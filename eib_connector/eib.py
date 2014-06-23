# -*- coding: utf-8 -*-
##############################################################################
#    
#    Copyright (C) 2013 Alessandro Camilli 
#    (<http://www.openforce.it>)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import fields, orm
from openerp.tools.translate import _
import cx_Oracle
import urllib
import urllib2
import base64
import json
import datetime

class eib_conn_log_move(orm.Model):
    
    _name = "eib.conn.log.move"
    _description = "EIB connector - Log move"
    _columns = {
        'date': fields.datetime('Date', readonly=True),
        'server_id': fields.many2one('eib.conn.server', 'Server', readonly=True),
        'last_sync_id': fields.integer('Last Sync Id', readonly=True),
        'partner_line_ids': fields.one2many('eib.conn.log.partner', 'move_id', 'Partner Lines', readonly=True),
    }
    _order = "date desc"
    
    def __set_ws_headers(self, eib_server, request):
        authKey = base64.b64encode( eib_server.ws_user + ":" + eib_server.ws_password)
        headers = {"Content-Type":"application/json", "Authorization":"Basic " + authKey}
        for key,value in headers.items():
            request.add_header(key,value)
        return request
        
    def _set_address(self, cr, uid, address_from_EIB):
            
            values = {
                    'is_company' : True,
                    #'ref' : element_to_import['ref'],
                    #'name' : partner_from_EIB['ragione_sociale'],
                    'street' : address_from_EIB['indirizzo'],
                    'city' : address_from_EIB['localita'],
                    'zip' : address_from_EIB['cap'],
                    #'province' : setup_province_id,
                    #'region' : setup_region_id,
                    #'country_id' : setup_country_id,
                    'phone' : address_from_EIB['telefono'],
                    'mobile' : address_from_EIB['cellulare'],
                    'fax' : address_from_EIB['fax'],
                    'email' : address_from_EIB['email'],
                    'website' : address_from_EIB['indirizzoWeb'],
                    #'fiscalcode' : partner_from_EIB['codiceFiscale'],
                    #'comment' : partner_from_EIB['note'],
                    }
            return values
    
    def _update_rel_address(self, cr, uid, address_id_from_EIB, partner_id):
            rel_address_obj = self.pool['eib.conn.rel.address']
            
            domain = [('eib_address_id', '=', address_id_from_EIB)]
            rel_address_ids = rel_address_obj.search(cr, uid, domain)
            rel = {
                'eib_address_id' : address_id_from_EIB,
                'partner_id' : partner_id,
                }
            if rel_address_ids:
                rel_address_obj.write(cr, uid, rel_address_ids, rel)
            else:
                rel_address_obj.create(cr, uid, rel)
            
            return True
    
    def _partner_from_address(self, cr, uid, address_from_EIB, partner_id):
            '''
            For not main address, it will create a new contact with partner_id how ref
            '''
            rel_address_obj = self.pool['eib.conn.rel.address']
            partner_obj = self.pool['res.partner']
            address_data = self._set_address(cr, uid, address_from_EIB)
            address_data['parent_id'] = partner_id
            
            # Search existing rel
            domain = [('eib_address_id', '=', address_from_EIB['id'])]
            rel_address_ids = rel_address_obj.search(cr, uid, domain)
            contact_id = False
            # If rel exists, update with the correct partner_id
            rel_address = False
            if rel_address_ids:
                rel_address = rel_address_obj.browse(cr, uid, rel_address_ids[0])
                contact_id = rel_address.partner_id.id
                if rel_address and contact_id:
                    partner_obj.write(cr, uid, [contact_id], address_data)
            
            # If new secondary address
            if not rel_address:
                # New contact
                val = {
                    'parent_id' : partner_id,
                    'name' : address_id_from_EIB['tipoIndirizzoDescIt']
                    }
                contact_id = partner_obj.create(cr, uid, val)
                if contact_id:
                    partner_obj.write(cr, uid, [contact_id], address_data)
                
            # Relation
            if contact_id:
                self._update_rel_address(cr, uid, address_from_EIB['id'], contact_id)
            else:
                return False
            
            return True
    
    def execute_sync(self, cr, uid, params, context=None):
        
        # Server
        eib_server_obj = self.pool['eib.conn.server']
        eib_server_ids = eib_server_obj.search(cr, uid, [('active','=', True)])
        
        for eib_server in eib_server_obj.browse(cr, uid, eib_server_ids):
            print "xx"
            try:
                dsn = cx_Oracle.makedsn(eib_server.host_name, eib_server.host_port, eib_server.host_sid)
                eib_db = cx_Oracle.connect(eib_server.host_user, eib_server.host_password, dsn)
            except cx_Oracle.DatabaseError, exc:
                error, = exc.args
                print 'sono in errore %s'%(error)
                
            # Last sync
            sync_move_ids = self.search(cr, uid, [], order="id desc", limit =1)
            last_sync_id = 0
            if len(sync_move_ids) > 0:
                sync_move = self.browse(cr, uid, sync_move_ids[0])
                last_sync_id = sync_move.last_sync_id
                
            # Move sync - create
            val = {
                'date': datetime.datetime.now(),
                'server_id': eib_server.id,
                }
            move_id = self.create(cr, uid, val)
            
            # Tables to syncronize >>> DA VERIFICARE: cosa sono UNITS
            tables_enabled = ['ANAGRAFICHE_SOGGETTI', 'CONTRAENTI', 'COMPAGNIE', 'PRODUTTORI', 'UNITS']
                
            sql = "SELECT * FROM ADM_HISTORY_MASTER \
                WHERE id > %d ORDER BY id " % (last_sync_id,)
            cursor = eib_db.cursor()
            cursor.execute(sql)
            last_id = False
            #>>> 100 x volta
            cont = 0
            
            for line in cursor:
                print line[0]
                if cont > 100: #>>>> da togliere
                    break
                #
                # >> DA TOGLIERE!!!!!!!!!!!!!!!!!<<<<
                if line[0] == 731656 :
                    import pdb
                    pdb.set_trace()
                
                log_id = line[0]
                table_name = line[4]
                table_record_id = int(line[5].replace('id:','')) 
                table_operation = line[3]
                eib_ref = {
                        'log_id' : log_id,
                        'table_name' : table_name,
                        'table_record_id' : table_record_id,
                        'table_operation' : table_operation,
                        }
                if table_name not in tables_enabled:
                    continue
                #
                # Drive to sync
                #
                if table_name == 'CONTRAENTI':
                    self.sync_contraente(cr, uid, eib_db, move_id, eib_server, eib_ref)
                    print "xxx"
                    cont += 1
                last_id = line[0]
                
                
                
                
            # Move sync - update with last id
            val = {
                'last_sync_id': last_id,
                }
            self.write(cr, uid, [move_id], val)
        
        return True
    
    def sync_contraente(self, cr, uid, eib_db, move_id, eib_server, eib_ref):
        
        if not eib_ref or not eib_ref['table_record_id']:
            return False
        
        partner_obj = self.pool['res.partner']
        rel_partner_obj = self.pool['eib.conn.rel.partner']
        rel_address_obj = self.pool['eib.conn.rel.address']
        log_partner_obj = self.pool['eib.conn.log.partner']
        
        def _set_partner(partner_from_EIB):
            # setup P.IVA 
            setup_vat = False
            if partner_from_EIB['partitaIva']:
                p_iva = '{:11s}'.format(partner_from_EIB['partitaIva'].zfill(11)) 
                setup_vat = 'IT' + p_iva #<<< da impostare in base al codice stato
            values = {
                    'is_company' : True,
                    'customer' : True,
                    #'ref' : element_to_import['ref'],
                    'name' : partner_from_EIB['ragioneSociale'],
                    #'street' : element_to_import['street'],
                    #'city' : setup_city,
                    #'zip' : setup_zip,
                    #'province' : setup_province_id,
                    #'region' : setup_region_id,
                    #'country_id' : setup_country_id,
                    #'phone' : row['phone'],
                    #'mobile' : row['mobile'],
                    #'fax' : row['fax'],
                    #'email' : row['email'],
                    'vat' : setup_vat,
                    'fiscalcode' : partner_from_EIB['codiceFiscale'],
                    'comment' : partner_from_EIB['note'],
                    }
            return values
        
        # Var for operation description
        log_desc = ""
        error = {
            'state' : False,
            'message' : ""
            }
        
        # Contraente from EIB database
        sql = "SELECT c.id, s.ragione_sociale FROM CONTRAENTI C \
                LEFT JOIN ANAGRAFICHE_SOGGETTI S ON (s.id = c.sogg_id) \
                WHERE c.id = %d " % (eib_ref['table_record_id'],)
        cursor = eib_db.cursor()
        cursor.execute(sql)
        eib_contraente = cursor.fetchone()
        log_desc += "%s (%d) " % (eib_contraente[1], eib_contraente[0])
        # Test existing rel
        domain = [('eib_partner_id', '=', eib_ref['table_record_id'])]
        rel_partner_ids = rel_partner_obj.search(cr, uid, domain)
        rel_partner = False
        if len(rel_partner_ids) > 0:
             rel_partner = rel_partner_obj.browse(cr, uid, rel_partner_ids[0])
        
        # Data from EIB
        url = eib_server.ws_base_url + 'anagrafiche/getContraente/' + str(eib_ref['table_record_id'])
        request = urllib2.Request(url)
        request = self.__set_ws_headers(eib_server, request)
        response = urllib2.urlopen(request)
        result = response.read()
        try:
            contraente = json.loads(result)
        except ValueError:
            error['state'] = True
            error['message'] = "Errore webservice contraente con id %d operazione %s " \
                 % (eib_ref['table_record_id'], eib_ref['table_operation'])
        
        # ... Dati anagrafici
        partner_id = False
        if not error['state']:
            dati_anagrafici = False
            if 'datiAnagrafici' in contraente:
                partner_data = _set_partner(contraente['datiAnagrafici'])
                if rel_partner :
                    try:
                        partner_obj.write(cr, uid, [rel_partner.partner_id.id], partner_data)
                        partner_id = rel_partner.partner_id.id
                    except Exception, e:
                        error['state'] = True
                        error['message'] = e[1]
                else:
                    try:
                        partner_id = partner_obj.create(cr, uid, partner_data)
                    except Exception, e:
                        error['state'] = True
                        error['message'] = e[1]
                    
        # Update Partner Relations
        if not error['state'] and not rel_partner:
            rel = {
                'eib_partner_id' : contraente['id'],
                'partner_id' : partner_id
               }
            rel_partner_id = rel_partner_obj.create(cr, uid, rel)      
                
        # ... Indirizzo principale
        if not error['state']:
            #     update dati del partner
            if partner_id and 'indirizzoPrincipale' in contraente:
                address_data = self._set_address(cr, uid, contraente['indirizzoPrincipale'])
                partner_obj.write(cr, uid, [partner_id], address_data)
                self._update_rel_address(cr, uid, contraente['indirizzoPrincipale']['id'], partner_id)
            # ... Indirizzo secondario
            if partner_id and ('indirizzoSecondario' in contraente):
                x = self._partner_from_address(cr, uid, contraente['indirizzoSecondario'], partner_id)
            # ... Indirizzo corrispondenza polizze
            if partner_id and ('corrispondenzaPolizze' in contraente):
                x = self._partner_from_address(cr, uid, contraente['corrispondenzaPolizze'], partner_id)
        
            val = {
                'move_id' : move_id,
                'partner_id': partner_id,
                'description': log_desc,
                'eib_log_id': eib_ref['log_id']
                }
            log_id = log_partner_obj.create(cr, uid, val)
        else:
            val = {
                'move_id' : move_id,
                'partner_id': partner_id or False,
                'description': log_desc,
                'eib_log_id': eib_ref['log_id'],
                'error' : error['state'],
                'error_message' : error['message']
                }
            log_id = log_partner_obj.create(cr, uid, val)
            return False
        
        return True
    
class eib_conn_server(orm.Model):
    
    _name = "eib.conn.server"
    _description = "EIB connector - Server"
    _columns = {
        'active': fields.boolean('Active'),
        'name': fields.char('Description', size=128, required=True),
        'host_name': fields.char('Host Name', size=32, required=True),
        'host_port': fields.integer('Host Port', required=True),
        'host_sid': fields.char('Host SID', required=True),
        'host_user': fields.char('Host Username', size=32, required=True),
        'host_password': fields.char('Host password', size=32, required=True),
        'ws_base_url': fields.char('Webservice base url', required=True),
        'ws_user': fields.char('Webservice user', required=True),
        'ws_password': fields.char('Webservice password', required=True),
        
        #'partner_contraente_category_ids': fields.many2many('res.partner.category', string='Categories'),
        #'partner_compagnia_category_ids': fields.many2many('res.partner.category', string='Categories'),
        #'partner_produttore_category_ids': fields.many2many('res.partner.category', string='Categories'),
    }
    _defaults = {
        'active': True,
    }
    
class eib_conn_log_partner(orm.Model):
    
    _name = "eib.conn.log.partner"
    _description = "EIB connector - Log partner"
    _columns = {
        'move_id': fields.many2one('eib.conn.log.move', 'Move Ref', readonly=True, ondelete='cascade'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True),
        'description': fields.text('Description'),
        'eib_log_id': fields.integer('EIB log id', help="Id from adm_hostory_master"),
        'error': fields.boolean('Error'),
        'error_message': fields.text('Error Message'),
    }
    
class eib_conn_rel_partner(orm.Model):
    
    _name = "eib.conn.rel.partner"
    _description = "EIB connector - Rel Partner"
    _columns = {
        'eib_partner_id': fields.integer('EIB partner id'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True),
    }
class eib_conn_rel_address(orm.Model):
    
    _name = "eib.conn.rel.address"
    _description = "EIB connector - Rel Address"
    _columns = {
        'eib_address_id': fields.integer('EIB address id'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True),
    }