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
from datetime import datetime
import pytz
import logging 
_logger = logging.getLogger(__name__)

class res_partner(orm.Model):
    
    _inherit = 'res.partner'
    _columns = {
            'eib_person_profession': fields.many2one('eib.conn.profession', string='Profession'),
        }
    
    def unlink(self, cr, uid, ids, *args, **kwargs):
        '''
        Remove Relation with eib
        '''
        rel_partner_obj = self.pool['eib.conn.rel.partner']
        rel_address_obj = self.pool['eib.conn.rel.address']
        
        for partner_id in ids:
            # Rel partner
            domain = [('partner_id', '=', partner_id)]
            rel_partner_ids = rel_partner_obj.search(cr, uid, domain)
            if rel_partner_ids:
                rel_partner_obj.write(cr, uid, rel_partner_ids, {'active': False})
            # Rel address
            domain = [('partner_id', '=', partner_id)]
            rel_address_ids = rel_address_obj.search(cr, uid, domain)
            if rel_address_ids:
                rel_address_obj.write(cr, uid, rel_address_ids, {'active': False})   
        return super(res_partner, self).unlink(cr, uid, ids, *args, **kwargs) 

class eib_conn_log_move(orm.Model):
    
    _name = "eib.conn.log.move"
    _description = "EIB connector - Log move"
    _columns = {
        'date': fields.datetime('Date', readonly=True),
        'server_id': fields.many2one('eib.conn.server', 'Server', readonly=True),
        'last_sync_id': fields.integer('Last Sync Id', readonly=True),
        'partner_line_ids': fields.one2many('eib.conn.log.partner', 'move_id', 'Partner Lines'),
    }
    _order = "date desc"
    
    def __set_ws_headers(self, eib_server, request):
        authKey = base64.b64encode( eib_server.ws_user + ":" + eib_server.ws_password)
        headers = {"Content-Type":"application/json", "Authorization":"Basic " + authKey}
        for key,value in headers.items():
            request.add_header(key,value)
        return request
        
    def _set_address(self, cr, uid, address_from_EIB):
        address_type_obj = self.pool['eib.conn.address.type']
        
        domain = [('code', '=', address_from_EIB['tipoIndirizzoSigla'])]
        address_type_ids = address_type_obj.search(cr, uid, domain, order='id desc')
        address_type = address_type_obj.browse(cr, uid, address_type_ids[0])
        
        values = {
                'is_company' : False,
                #'ref' : element_to_import['ref'],
                'street' : address_from_EIB['indirizzo'],
                'street2' : address_from_EIB['estensione'] or False,
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
        # name : 
        # If not main address, take name of address type
        if not address_type.main:
            values['name'] = address_from_EIB['tipoIndirizzoDescIt']
        else:
            values['is_company'] = True
        return values
    
    
    def execute_sync(self, cr, uid, params, context=None):
        '''
        The first sync imports only the configuration tables.
        After the oppropriate setting, it's possible to execute other sync
        '''
        # Server
        eib_server_obj = self.pool['eib.conn.server']
        eib_server_ids = eib_server_obj.search(cr, uid, [('active','=', True)])
        
        for eib_server in eib_server_obj.browse(cr, uid, eib_server_ids):
            
            try:
                dsn = cx_Oracle.makedsn(eib_server.host_name, eib_server.host_port, eib_server.host_sid)
                eib_db = cx_Oracle.connect(eib_server.host_user, eib_server.host_password, dsn)
            except cx_Oracle.DatabaseError, exc:
                error, = exc.args
                print 'sono in errore %s'%(error)
                
            # TEST POST contraente
            dati_anagrafici = {
                'ragioneSociale' : "Alex SPA",
                'nome' : "Alessandro",
                'cognome' : "Camilli",
                'sesso' : "M",
                }
            dati_indirizzo_principale = {
                'indirizzo' : "Via G.Mazzini, 2",
                'localita' : "Pedaso"
                }
            url = eib_server.ws_base_url + 'anagrafiche/postContraente/'
            '''
            request = urllib2.Request(url)
            request = self.__set_ws_headers(eib_server, request)
            response = urllib2.urlopen(request)
            result = response.read()
            try:
                contraente = json.loads(result)
            except ValueError:
                log_message['error'] = True
                log_message['message'] = _("Webservice Error : ") 
                '''
            # Last sync
            sync_move_ids = self.search(cr, uid, [], order="id desc", limit =1)
            last_sync_id = 0
            if len(sync_move_ids) > 0:
                sync_move = self.browse(cr, uid, sync_move_ids[0])
                last_sync_id = sync_move.last_sync_id
            
            # Config Control setting
            eib_server_obj.config_control(cr, uid, [eib_server.id], context=None)
                
            # Move sync - create
            val = {
                'date': datetime.now(),
                'server_id': eib_server.id,
                }
            move_id = self.create(cr, uid, val)
            
            # Sync config tables
            eib_server_obj.sync_config_table(cr, uid, [eib_server.id], context=None)
            
            #
            # Tables to syncronize >>> DA VERIFICARE: cosa sono UNITS
            #
            tables_enabled = ['ANAGRAFICHE_SOGGETTI', 'CONTRAENTI', 'COMPAGNIE', 'PRODUTTORI', 'UNITS']
                
            sql = "SELECT * FROM ADM_HISTORY_MASTER \
                WHERE id > %d ORDER BY id " % (last_sync_id,)
            cursor = eib_db.cursor()
            cursor.execute(sql)
            last_id = False
            #>>> 100 x volta
            cont = 0
            
            for line in cursor:
                print str(cont) + ". " + str(line[0])
                if cont > 180: #>>>> da togliere
                    break
                #>>>>
                #if line[0] == 732051:
                    #import pdb
                    #pdb.set_trace()
                #<<<<
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
                    self.sync_contraente(cr, uid, eib_db, move_id, eib_server, eib_ref, context)
                    cont += 1
                elif table_name == 'COMPAGNIE':
                    self.sync_compagnia(cr, uid, eib_db, move_id, eib_server, eib_ref, context)
                    cont += 1
                elif table_name == 'PRODUTTORI':
                    #
                    # >>>>>>>> sospesa x ORA in attesa del webservice
                    # self.sync_produttore(cr, uid, eib_db, move_id, eib_server, eib_ref, context)
                    cont += 1
                last_id = line[0]
            #
            # Account moves
            #
            self.sync_registrazioni_contabili(cr, uid, eib_db, move_id, eib_server, context)
            
            # Move sync - update with last id
            val = {
                'last_sync_id': last_id,
                }
            self.write(cr, uid, [move_id], val)
            
            # Mail Log
            eib_server_obj.mail_alert(cr, uid, [eib_server.id], [move_id], context=None)
        
        return True 
    
    def sync_registrazioni_contabili(self, cr, uid, eib_db, move_id, eib_server, context=None):
        
        sql = "SELECT * FROM WS_ACGV4_GIMOX00F \
                WHERE trasferito is null \
                ORDER BY nureg, rireg "
        cursor = eib_db.cursor()
        cursor.execute(sql)
        
        for line in cursor:
            print "xx"
        
            
        return True
    
    def sync_contraente(self, cr, uid, eib_db, move_id, eib_server, eib_ref, context=None):
        
        log_partner_obj = self.pool['eib.conn.log.partner']
        if not context:
            context = {}
        # Import
        # ...categories
        categories = []
        for category in eib_server.partner_contraente_category_ids:
            categories.append(category.category_id.id)
        
        import_setting = {
                'customer' : True,             
                'category_ids' : categories,             
                }
        context.update({'import_setting' : import_setting})
        log_id = self.import_partner(cr, uid, eib_db, move_id, eib_server, eib_ref, context)
        
        return True
    
    def sync_compagnia(self, cr, uid, eib_db, move_id, eib_server, eib_ref, context=None):
        
        log_partner_obj = self.pool['eib.conn.log.partner']
        if not context:
            context = {}
        # Import
        # ...categories
        categories = []
        for category in eib_server.partner_compagnia_category_ids:
            categories.append(category.category_id.id)
        
        import_setting = {
                'supplier' : True,             
                'category_ids' : categories,             
                }
        context.update({'import_setting' : import_setting})
        log_id = self.import_partner(cr, uid, eib_db, move_id, eib_server, eib_ref, context)
        
        return True
    
    def sync_produttore(self, cr, uid, eib_db, move_id, eib_server, eib_ref, context=None):
        
        log_partner_obj = self.pool['eib.conn.log.partner']
        if not context:
            context = {}
        # Import
        # ...categories
        categories = []
        for category in eib_server.partner_produttore_category_ids:
            categories.append(category.category_id.id)
        
        import_setting = {
                'supplier' : True,             
                'category_ids' : categories,             
                }
        context.update({'import_setting' : import_setting})
        log_id = self.import_partner(cr, uid, eib_db, move_id, eib_server, eib_ref, context)
        
        return True
    
    def import_partner(self, cr, uid, eib_db, move_id, eib_server, eib_ref, context=None):
        
        partner_obj = self.pool['res.partner']
        rel_partner_obj = self.pool['eib.conn.rel.partner']
        rel_address_obj = self.pool['eib.conn.rel.address']
        log_partner_obj = self.pool['eib.conn.log.partner']
        
        if context:
            import_setting = context.get('import_setting')
        
        def _normalize_data(partner_from_EIB, import_setting):
            # Wrong Fiscalcode
            if not len(soggetto['datiAnagrafici']['codiceFiscale']) == 16 \
                and not len(soggetto['datiAnagrafici']['codiceFiscale']) == 11:
                soggetto['datiAnagrafici']['codiceFiscale'] = ''
            return soggetto
        
        def _set_partner(partner_from_EIB, import_setting):
            profession_obj = self.pool['eib.conn.profession']
            # setup P.IVA 
            setup_vat = False
            if partner_from_EIB['partitaIva']:
                p_iva = '{:11s}'.format(partner_from_EIB['partitaIva'].zfill(11)) 
                setup_vat = 'IT' + p_iva #<<< da impostare in base al codice stato
            # persona giuridica/fisica
            setup_persona = False
            if partner_from_EIB['persona'] == 'G':
                setup_persona = 'legal'
            else:
                setup_persona = 'individual'
            # stato civile
            setup_marital_status = False
            if partner_from_EIB['statoCivile'] == '1':
                setup_marital_status = 'single'
            elif partner_from_EIB['statoCivile'] == '2':
                setup_marital_status = 'married'
            elif partner_from_EIB['statoCivile'] == '3':
                setup_marital_status = 'widower'
            elif partner_from_EIB['statoCivile'] == '4':
                setup_marital_status = 'divorced'
            # Profession
            setup_profession = False
            domain = [('code', '=', partner_from_EIB['professioneSigla'])]
            prof_ids = profession_obj.search(cr, uid, domain)
            if prof_ids:
                prof = profession_obj.browse(cr, uid, prof_ids[0])
                setup_profession = prof.id
            # Date of birth
            setup_date_of_birth = False
            if partner_from_EIB['dataNascita']:
                tz_italy = pytz.timezone("Europe/Rome")
                date_of_birth = datetime.fromtimestamp(\
                                            partner_from_EIB['dataNascita']/1000, tz_italy)
                #setup_date_of_birth = date_work.astimezone(italy)
                setup_date_of_birth = date_of_birth.isoformat()
                date_limit = datetime.strptime('1900-01-01', "%Y-%m-%d")
                if date_of_birth.date() <= date_limit.date():
                    setup_date_of_birth = False
            # Setting values
            values = {
                    'is_company' : True,
                    'name' : partner_from_EIB['ragioneSociale'],
                    'vat' : setup_vat,
                    'fiscalcode' : partner_from_EIB['codiceFiscale'] or False,
                    'comment' : partner_from_EIB['note'],
                    'person_type' : setup_persona,
                    'person_surname' : partner_from_EIB['cognome'],
                    'person_name' : partner_from_EIB['nome'],
                    'person_gender' : partner_from_EIB['sesso'],
                    'person_marital_status' : setup_marital_status,
                    'person_profession' : setup_profession,
                    'person_date_of_birth': setup_date_of_birth,
                    #>>>> mancano
                    #'person_city_of_birth': fields.char('City of birth', size=64),
                    #'person_province_of_birth': fields.many2one('res.province', string='Province'),
                    #'person_region_of_birth': fields.many2one('res.region', string='Region'),
                    #'person_country_of_birth': fields.many2one('res.country', string='Country'),
                    #<<<<
                    }
            # Other setting
            if 'customer' in import_setting:
                values['customer'] = import_setting['customer']
            if 'supplier' in import_setting:
                values['supplier'] = import_setting['supplier']
            if 'category_ids' in import_setting and import_setting['category_ids']:
                values['category_id'] = [(6, 0, import_setting['category_ids'])]
                
            # State from eib
            if partner_from_EIB['attivo'] == 0:
                values['customer'] = False
                values['supplier'] = False
            return values
        
        # Var for operation description
        log_desc = ""
        log_rel_partner = []
        log_rel_address = []
        log_message = {
            'error' : False,
            'message' : "",
            'message_error' : False,
            'message_chain' : False,
            'message_normal' : True,
            }
        
        # Contraente from EIB database
        sql = "SELECT c.id, s.ragione_sociale FROM %s C \
                LEFT JOIN ANAGRAFICHE_SOGGETTI S ON (s.id = c.sogg_id) \
                WHERE c.id = %d " % (eib_ref['table_name'], eib_ref['table_record_id'],)
        cursor = eib_db.cursor()
        cursor.execute(sql)
        eib_soggetto = cursor.fetchone()
        log_desc += "%s (%d) " % (eib_soggetto[1], eib_soggetto[0])
        # Test existing rel
        domain = [('eib_partner_id', '=', eib_ref['table_record_id']), ('active', '=', True)]
        rel_partner_ids = rel_partner_obj.search(cr, uid, domain)
        rel_partner = False
        if len(rel_partner_ids) > 0:
             rel_partner = rel_partner_obj.browse(cr, uid, rel_partner_ids[0])
        
        # Data from EIB
        if eib_ref['table_name'] == 'CONTRAENTI':
            url = eib_server.ws_base_url + 'anagrafiche/getContraente/' + str(eib_ref['table_record_id'])
        elif eib_ref['table_name'] == 'COMPAGNIE':
            url = eib_server.ws_base_url + 'anagrafiche/getCompagnia/' + str(eib_ref['table_record_id'])
        request = urllib2.Request(url)
        request = self.__set_ws_headers(eib_server, request)
        response = urllib2.urlopen(request)
        result = response.read()
        
        try:
            soggetto = json.loads(result)
            soggetto = _normalize_data(soggetto, context.get('import_setting', False))
        except ValueError:
            log_message['error'] = True
            log_message['message'] = _("Webservice Error %s:  id %d and operation %s ") \
                 % (eib_ref['table_name'], eib_ref['table_record_id'], eib_ref['table_operation'])
        # Partner exists with the same VAT
        if not log_message['error'] and not rel_partner \
            and soggetto['datiAnagrafici']['partitaIva']:
            domain = [('vat', 'like', '%' + soggetto['datiAnagrafici']['partitaIva']),
                       ('is_company', '=', True)]
            existing_partner_by_vat_ids = partner_obj.search(cr, uid, domain)
            if existing_partner_by_vat_ids:
                rel_id = rel_partner_obj.create_rel(cr, 
                                           uid, 
                                           existing_partner_by_vat_ids[0], 
                                           soggetto['id'])
                rel_partner = rel_partner_obj.browse(cr, uid, rel_id)
                log_desc += _("Linked to Partner %s con P.I. %s") % \
                    (rel_partner.partner_id.name, soggetto['datiAnagrafici']['partitaIva'])
                log_message['message_chain'] = True
                log_rel_partner.append(rel_id)
        # Partner exists with the same FISCALCODE
        if not log_message['error'] and not rel_partner \
            and soggetto['datiAnagrafici']['codiceFiscale']:
            domain = [('fiscalcode', '=', soggetto['datiAnagrafici']['codiceFiscale']),
                       ('is_company', '=', True)]
            existing_partner_by_fc_ids = partner_obj.search(cr, uid, domain)
            if existing_partner_by_fc_ids:
                rel_id = rel_partner_obj.create_rel(cr, 
                                           uid, 
                                           existing_partner_by_fc_ids[0], 
                                           soggetto['id'])
                rel_partner = rel_partner_obj.browse(cr, uid, rel_id)
                log_desc += _("Linked to Partner %s con FISCALCODE %s") % \
                    (rel_partner.partner_id.name, soggetto['datiAnagrafici']['codiceFiscale'])
                log_message['message_chain'] = True
                log_rel_partner.append(rel_id)
                
        # ... Dati anagrafici
        partner_id = False
        if not log_message['error']:
            dati_anagrafici = False
            if 'datiAnagrafici' in soggetto:
                partner_data = _set_partner(soggetto['datiAnagrafici'], context.get('import_setting', False))
                if rel_partner :
                    try:
                        partner_obj.write(cr, uid, [rel_partner.partner_id.id], partner_data)
                        partner_id = rel_partner.partner_id.id
                    except Exception, e:
                        log_message['error'] = True
                        log_message['message'] = e[1]
                else:
                    try:
                        partner_id = partner_obj.create(cr, uid, partner_data)
                    except Exception, e:
                        log_message['error'] = True
                        log_message['message'] = e[1]
                    
        # Update Partner Relations
        if not log_message['error'] and not rel_partner:
            rel = {
                'eib_partner_id' : soggetto['id'],
                'partner_id' : partner_id
               }
            rel_partner_id = rel_partner_obj.create(cr, uid, rel)
            log_rel_partner.append(rel_partner_id)      
                
        # ... Indirizzo principale
        if not log_message['error']:
            #     update dati del partner
            if partner_id and 'indirizzoPrincipale' in soggetto and soggetto['indirizzoPrincipale']:
                address_data = self._set_address(cr, uid, soggetto['indirizzoPrincipale'])
                partner_obj.write(cr, uid, [partner_id], address_data)
                rel_address_obj.create_rel(cr, uid,
                                        partner_id,
                                        soggetto['indirizzoPrincipale']['id'])
            if not soggetto['indirizzoPrincipale']:
                soggetto.update({'indirizzoPrincipale': {'id': 0}})
            
            # Altri indirizzi diversi da quello principale : Creazione contatti
            sql = "SELECT i.id AS i0, i.estensione AS i1, \
                    i.indirizzo AS i2, i.cap AS i3, i.localita AS i4, \
                    i.email AS i5, i.cellulare AS i6, \
                    i.telefono AS i7, i.fax AS i8,  \
                    i.indirizzo_web AS i9, i.tpin_id AS i10, \
                    t.denominazione_it AS i11, t.sigla AS i12 \
                    FROM INDIRIZZI i \
                    LEFT JOIN tipi_indirizzi t ON (t.id = i.tpin_id) \
                    WHERE i.anso_id = %d AND i.id <> %d " \
                    % (soggetto['id'], soggetto['indirizzoPrincipale']['id'])
            cursor = eib_db.cursor()
            cursor.execute(sql)
            for element in cursor.fetchall():
                address_from_EIB = {
                            'id' : element[0],        
                            'estensione' : element[1],        
                            'indirizzo' : element[2],        
                            'cap' : element[3],
                            'localita' : element[4],
                            'email' : element[5],
                            'cellulare' : element[6],        
                            'telefono' : element[7],     
                            'fax' : element[8],
                            'indirizzoWeb' : element[9],        
                            'tipoIndirizzoId' : element[10],        
                            'tipoIndirizzoDescIt' : element[11],        
                            'tipoIndirizzoSigla' : element[12],        
                            }
                #res = self._partner_from_address(cr, uid, address_from_EIB, partner_id)
                # 
                address_data = self._set_address(cr, uid, address_from_EIB)
                address_data['parent_id'] = partner_id
                # Search existing address rel
                domain = [('eib_address_id', '=', address_from_EIB['id']), ('active', '=', True)]
                rel_address_ids = rel_address_obj.search(cr, uid, domain)
                contact_id = False
                # If rel exists, update with the correct partner_id
                if rel_address_ids:
                    rel_address = rel_address_obj.browse(cr, uid, rel_address_ids[0])
                    contact_id = rel_address.partner_id.id
                    if rel_address and contact_id:
                        partner_obj.write(cr, uid, [contact_id], address_data)
                else:
                    # New contact e new relation
                    val = {
                        'parent_id' : partner_id,
                        'name' : address_from_EIB['tipoIndirizzoDescIt']
                        }
                    contact_id = partner_obj.create(cr, uid, val)
                    if contact_id:
                        partner_obj.write(cr, uid, [contact_id], address_data)
                        rel_id = rel_address_obj.create_rel(cr, uid, contact_id, address_from_EIB['id'])
                        log_rel_address.append(rel_id)
                    
        # Log
        if not log_message['error']:    
            val = {
                'move_id' : move_id,
                'partner_id': partner_id,
                'description': log_desc,
                'eib_log_id': eib_ref['log_id'],
                'eib_table': eib_ref['table_name'],
                'rel_partner_ids': [(6, 0, log_rel_partner)],
                'rel_address_ids': [(6, 0, log_rel_address)],
                #'message_type': 'normal'
                }
            if log_message['message_chain']:
                val['message_type'] = 'chain'
            else:
                val['message_type'] = 'normal'
            log_id = log_partner_obj.create(cr, uid, val)
        else:
            val = {
                'move_id' : move_id,
                'partner_id': partner_id or False,
                'description': log_desc,
                'eib_log_id': eib_ref['log_id'],
                'eib_table': eib_ref['table_name'],
                'error' : log_message['error'],
                'error_message' : log_message['message'],
                'message_type': 'error'
                }
            log_id = log_partner_obj.create(cr, uid, val)
        
        return log_id
    
class eib_conn_server(orm.Model):
    
    def _check_mail_message_from(self, cr, uid, ids, context=None):
        server_mail_obj = self.pool['ir.mail_server']
        
        for element in self.browse(cr, uid, ids, context=context):
            serv_ids = server_mail_obj.search(cr, uid, [('smtp_user', '=', element.mail_message_from)], order='sequence', limit=1)
            if not serv_ids:
                return False
        return True
    
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
        
        'mail_message_from': fields.char('Mail From'),
        'mailing_list_ids': fields.one2many('eib.conn.server.mailing', 'server_id', string='Mailing List'),
        
        'partner_contraente_category_ids': fields.one2many('eib.conn.server.category.contraente', 'server_id', string='Contraente Categories'),
        'partner_compagnia_category_ids': fields.one2many('eib.conn.server.category.compagnia', 'server_id',  string='Compagnia Categories'),
        'partner_produttore_category_ids': fields.one2many('eib.conn.server.category.produttore', 'server_id', string='Produttore Categories'),
        
    }
    _defaults = {
        'active': True,
    }
    _constraints = [
        (_check_mail_message_from, 'Error! Any mail server out for this e-mail address ', ['mail_message_from']),
    ]
    
    def sync_config_table(self, cr, uid, ids, context):
        
        address_type_obj = self.pool['eib.conn.address.type']
        profession_obj = self.pool['eib.conn.profession']
        
        for eib_server in self.browse(cr, uid, ids):
            try:
                dsn = cx_Oracle.makedsn(eib_server.host_name, eib_server.host_port, eib_server.host_sid)
                eib_db = cx_Oracle.connect(eib_server.host_user, eib_server.host_password, dsn)
            except cx_Oracle.DatabaseError, exc:
                error, = exc.args
                print 'sono in errore %s'%(error)
            
            address_type_obj.sync(cr, uid, eib_db)
            profession_obj.sync(cr, uid, eib_db)
            
        return True
    
    def config_control(self, cr, uid, ids, context):
        '''
        Configuration control
        '''
        address_type_obj = self.pool['eib.conn.address.type']
        res = False
        
        # All types address with appropriate odoo type
        domain = [('rel_type', '=', False)]
        address_ids = address_type_obj.search(cr, uid, domain)
        if address_ids :
            raise orm.except_orm(_('Error Address Type Config!'),_("Missing some relation type"))
        
        return res
    
    def mail_alert(self, cr, uid, ids, move_ids=[], context=None):
        log_partner_obj = self.pool['eib.conn.log.partner']
        if not context :
            context = {}
        for server in self.browse(cr, uid, ids):
            for mail_to in server.mailing_list_ids:
                context.update({'mail_to' : mail_to.mail})
                context.update({'mail_subject' : 'EIB Log Sync'})
                # One type message required
                if not mail_to.message_type_error\
                    and not mail_to.message_type_chain\
                    and not mail_to.message_type_normal:
                    continue
                partner_msg_ids = []
                if mail_to.message_type_error:
                    domain = [('move_id', 'in', move_ids), ('message_type', '=', 'error')]
                    msg_error_ids = log_partner_obj.search(cr, uid, domain)
                    if msg_error_ids:
                        partner_msg_ids += msg_error_ids
                if mail_to.message_type_chain:
                    domain = [('move_id', 'in', move_ids), ('message_type', '=', 'chain')]
                    msg_chain_ids = log_partner_obj.search(cr, uid, domain)
                    if msg_chain_ids:
                        partner_msg_ids += msg_chain_ids
                if mail_to.message_type_normal:
                    domain = [('move_id', 'in', move_ids), ('message_type', '=', 'normal')]
                    msg_normal_ids = log_partner_obj.search(cr, uid, domain)
                    if msg_normal_ids:
                        partner_msg_ids += msg_normal_ids
                if partner_msg_ids:
                    context.update({'partner_msg_ids' : partner_msg_ids})
                    
                self.send_alert_mail(cr, uid, ids, context)
                    
        # Partner
        
        #line_ids = log_partner_obj.search(cr, uid, [('state', '=', '2binvoiced'),'|',('due_date','<=', today.strftime('%Y-%m-%d')), ('due_date','=', False) ])
        #self.send_alert_mail(cr, uid, line_ids)
        
        return True
    
    def send_alert_mail(self, cr, uid, ids, context=None):
        
        mail_obj = self.pool['mail.mail']
        mail_message_obj = self.pool['mail.message']
        email_template_obj = self.pool['email.template']
        email_compose_message_obj = self.pool['mail.compose.message']
        server_mail_obj = self.pool['ir.mail_server']
        log_partner_obj = self.pool['eib.conn.log.partner']
        
        partner_msg_ids = context.get('partner_msg_ids', False)
        mail_ids = []
        for server in self.browse(cr, uid, ids):
            
            # Server mail smtp
            if server.mail_message_from:
                serv_ids = server_mail_obj.search(cr, uid, [('smtp_user', '=', server.mail_message_from)], order='sequence', limit=1)
                if serv_ids:
                    user_server_mail = server_mail_obj.browse(cr, uid, serv_ids[0])
            
            if not user_server_mail:
                raise orm.except_orm(_('Error Creating Alert Message!'),_("Missing Address mail from in the Server Configuration"))
            
            # Message
            message_vals = {
                    'type': 'email',
                    #'email_from': contract.manager_id.email,
                    'subject' : context.get('mail_subject', False),
                    }
            message_id = mail_message_obj.create(cr, uid, message_vals)
            
            # E-mail
            mail_to = context.get('mail_to', False)
            mail_subject = context.get('mail_subject', False)
            # Body
            mail_body = "<p>test mail di prova</p>"
            cell_standard = "<td style='border:1px solid;'> %s </>"
            # ... Messages from partner sync 
            if partner_msg_ids:
                mail_body += "<h3>Sincronizzazione Partners </h3>"
                mail_body += "<table> \
                        <th>Tipo</th><th>Tabella</th><th>Descrizione</th><th>Errore</th>"
                for msg in log_partner_obj.browse(cr, uid, partner_msg_ids):
                    mail_body += "<tr>"
                    # Type
                    if msg.message_type == 'error':
                        mail_body += "<td><b>" + msg.message_type + "</b></td>" 
                    else:
                        mail_body += "<td></td>"
                    # Table name
                    if msg.eib_table:
                        mail_body += "<td>" + msg.eib_table + "</td>"
                    else:
                        mail_body += "<td></td>"
                    # Other info
                    if msg.description:
                        mail_body += "<td>" + msg.description + "</td>"
                        #mail_body += cell_standard % ( msg.description )
                    else:
                        mail_body += "<td></td>"
                    if msg.error_message:
                        mail_body += "<td>" + msg.error_message + "</td>"
                    else:
                        mail_body += "<td></td>"
                    
                    mail_body += "</tr>"
                mail_body += "</table>"
                
            mail_id = mail_obj.create(cr, uid, {
                            'mail_message_id' : message_id,
                            'mail_server_id' : user_server_mail and user_server_mail.id or False,
                            'state' : 'outgoing',
                            #'auto_delete' : email_template.auto_delete,
                            'auto_delete' : True,
                            #'email_from' : mail_from,
                            #'email_to' : follower.email,
                            'email_to' : mail_to,
                            #'reply_to' : reply_to,
                            'body_html' : mail_body,
                            })
       
            mail_ids += [mail_id,]
            if mail_ids:
                mail_obj.send(cr, uid, mail_ids)
                print "Xxx" 
        
                _logger.info('[SUBSCRIPTION SEND MAIL] Sended %s mails for EIB log' % (len(mail_ids) ))
        res ={}
        
        return res
        
        
        '''
        # email template
        email_template = False
        email_template_ids = email_template_obj.search(cr, uid, [('model', '=', 'relate.contract.payment.term')])
        if email_template_ids:
            email_template = email_template_obj.browse(cr, uid, email_template_ids[0])
        
        mail_ids= []
        
        for line in self.browse(cr, uid, ids):
            
            contract = line.contract_id
            
            # user's mail server
            if contract.manager_id.email:
                serv_ids = server_mail_obj.search(cr, uid, [('smtp_user', '=', contract.manager_id.email)], order='sequence', limit=1)
                if serv_ids:
                    user_server_mail = server_mail_obj.browse(cr, uid, serv_ids[0])
            
            for follower in contract.message_follower_ids:
                
                if not follower.email:
                    continue
                
                mail_subject = email_compose_message_obj.render_template(cr,uid,_(email_template.subject),'relate.contract.payment.term',line.id)
                mail_body = email_compose_message_obj.render_template(cr,uid,_(email_template.body_html),'relate.contract.payment.term',line.id)
                mail_to = email_compose_message_obj.render_template(cr,uid,_(email_template.email_to),'relate.contract.payment.term',line.id)
                reply_to = email_compose_message_obj.render_template(cr,uid,_(email_template.reply_to),'relate.contract.payment.term',line.id)
                if contract.manager_id.email:
                    mail_from = contract.manager_id.email
                else:
                    mail_from = email_compose_message_obj.render_template(cr,uid,_(email_template.email_from),'relate.contract.payment.term',line.id)
                
                if not mail_from:
                    continue
                
                # body with data line
                
                mail_body += '<h3>Contratto %s </h3>' % (contract.name)
                due_date = datetime.strptime(line.due_date, "%Y-%m-%d")   
                mail_body += '<div><h2> %s </h2></div>' % (line.name, )
                mail_body += '<div><h3> Scadenza %s - Importo %s </h3></div>' % ( due_date.strftime('%d-%m-%Y'), '{:16.2f}'.format(line.amount) )
                
                message_vals = {
                        'type': 'email',
                        'email_from': contract.manager_id.email,
                        'subject' : 'Contratto da fatturare',
                        }
                message_id = mail_message_obj.create(cr, uid, message_vals)
                
                mail_id = mail_obj.create(cr, uid, {
                        'mail_message_id' : message_id,
                        'mail_server_id' : user_server_mail and user_server_mail.id or email_template.mail_server_id and email_template.mail_server_id.id or False,
                        'state' : 'outgoing',
                        'auto_delete' : email_template.auto_delete,
                        'email_from' : mail_from,
                        'email_to' : follower.email,
                        #'reply_to' : reply_to,
                        'body_html' : mail_body,
                        })
                
                mail_ids += [mail_id,]
        
        if mail_ids:
            mail_obj.send(cr, uid, mail_ids)
            print "Xxx"
        
        _logger.info('[SUBSCRIPTION SEND MAIL] Sended %s mails for %s template' % (len(mail_ids), email_template.name))
        res ={}
        
        return res'''
    def on_change_mail_message_from(self, cr, uid, ids, mail_message_from, context=None):
        '''
        The Mail must be present on mail server out
        '''
        server_mail_obj = self.pool['ir.mail_server']
        val = {}
        if mail_message_from:
            serv_ids = server_mail_obj.search(cr, uid, [('smtp_user', '=', mail_message_from)], order='sequence', limit=1)
            if not serv_ids:
                raise orm.except_orm(_('Error!'),_("Any mail server out for this e-mail address"))
                val = {
                    #'mail_message_from':"",
                    }
            
        res ={}
        res = {'value': val}
        return res
    
class eib_conn_server_category_contraente(orm.Model):
    
    _name = "eib.conn.server.category.contraente"
    _description = "EIB connector - Server - Category Contraente"
    _columns = {
        'server_id': fields.many2one('eib.conn.server', 'Server', readonly=True, ondelete='cascade'),
        'category_id': fields.many2one('res.partner.category', 'Category'),
    }

class eib_conn_server_category_compagnia(orm.Model):
    
    _name = "eib.conn.server.category.compagnia"
    _description = "EIB connector - Server - Category Compagnia"
    _columns = {
        'server_id': fields.many2one('eib.conn.server', 'Server', readonly=True, ondelete='cascade'),
        'category_id': fields.many2one('res.partner.category', 'Category'),
    }
class eib_conn_server_category_produttore(orm.Model):
    
    _name = "eib.conn.server.category.produttore"
    _description = "EIB connector - Server - Category Produttore"
    _columns = {
        'server_id': fields.many2one('eib.conn.server', 'Server', readonly=True, ondelete='cascade'),
        'category_id': fields.many2one('res.partner.category', 'Category'),
    }
     
class eib_conn_server_mailing(orm.Model):
    
    _name = "eib.conn.server.mailing"
    _description = "EIB connector - Server - Mailing"
    _columns = {
        'server_id': fields.many2one('eib.conn.server', 'Server', readonly=True, ondelete='cascade'),
        'mail': fields.char('Mail address'),
        'message_type_error': fields.boolean('Message Error'),
        'message_type_chain': fields.boolean('Message Chain'),
        'message_type_normal': fields.boolean('Message Normal'),
    }
    
    
class eib_conn_log_partner(orm.Model):
    
    _name = "eib.conn.log.partner"
    _description = "EIB connector - Log partner"
    _columns = {
        'move_id': fields.many2one('eib.conn.log.move', 'Move Ref', readonly=True, ondelete='cascade'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True),
        'description': fields.text('Description', readonly=True), 
        'eib_log_id': fields.integer('EIB log id', help="Id from adm_hostory_master"),
        'eib_table': fields.char('EIB Table', size=128, readonly=True),
        'error': fields.boolean('Error'),
        'error_message': fields.text('Error Message', readonly=True),
        'message_type' : fields.selection([
            ('normal','Normal'),
            ('error','Error'),
            ('chain','Chain'),
            ], 'Message Type', readonly=True),
        'rel_partner_ids': fields.one2many('eib.conn.rel.partner', 'log_partner_id', 'Partner Relations' ),
        'rel_address_ids': fields.one2many('eib.conn.rel.address', 'log_address_id', 'Partner Relations' ),
    }
    _defaults = {
        'message_type' : 'normal'
    }
    
class eib_conn_rel_partner(orm.Model):
    
    def _check_one_rel(self, cr, uid, ids, context=None):
        for element in self.browse(cr, uid, ids, context=context):
            element_ids = self.search(cr, uid, [('active','=', True),('eib_partner_id','=', element.eib_partner_id)], context=context)
            if len(element_ids) > 1:
                return False
        return True
    
    _name = "eib.conn.rel.partner"
    _description = "EIB connector - Rel Partner"
    _columns = {
        'active': fields.boolean('Active'),
        'eib_partner_id': fields.integer('EIB partner id'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True),
        'log_partner_id': fields.many2one('eib.conn.log.partner', 'Log partner', ondelete='cascade'),
    }
    _defaults = {
        'active' : True
    }
    _constraints = [
        (_check_one_rel, 'Error! Relation already exists for EIB partner ', ['eib_partner_id']),
    ]
    
    def create_rel(self, cr, uid, partner_id, eib_partner_id, context=None):
        
        if not partner_id or not eib_partner_id:
            return False
        domain = [('eib_partner_id', '=', eib_partner_id)] 
        rel_ids = self.search(cr, uid, domain)
        if rel_ids:
            rel_id = rel_ids[0]
            self.write(cr, uid, rel_ids, {'partner_id' : partner_id})
        else:
            vals = {
                'partner_id' : partner_id,
                'eib_partner_id' : eib_partner_id,
                }
            rel_id = self.create(cr, uid, vals)
            
        return rel_id
    
class eib_conn_rel_address(orm.Model):
    
    def _check_one_rel(self, cr, uid, ids, context=None):
        for element in self.browse(cr, uid, ids, context=context):
            element_ids = self.search(cr, uid, [('active','=', True),('eib_address_id','=', element.eib_address_id)], context=context)
            if len(element_ids) > 1:
                return False
        return True
    
    _name = "eib.conn.rel.address"
    _description = "EIB connector - Rel Address"
    _columns = {
        'active': fields.boolean('Active'),
        'eib_address_id': fields.integer('EIB address id'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True),
        'log_address_id': fields.many2one('eib.conn.log.partner', 'Log address', ondelete='cascade'),
    }
    _defaults = {
        'active' : True
    }
    _constraints = [
        (_check_one_rel, 'Error! Relation already exists for EIB Address ', ['eib_address_id']),
    ]
    
    def create_rel(self, cr, uid, partner_id, address_id_from_EIB):
            
        domain = [('eib_address_id', '=', address_id_from_EIB), ('active', '=', True)]
        rel_ids = self.search(cr, uid, domain)
        rel = {
            'eib_address_id' : address_id_from_EIB,
            'partner_id' : partner_id,
            }
        if rel_ids:
            rel_id = rel_ids[0]
            self.write(cr, uid, rel_ids, rel)
        else:
            rel_id = self.create(cr, uid, rel)
        
        return rel_id
    
class eib_conn_profession(orm.Model):
    
    _name = "eib.conn.profession"
    _description = "EIB connector - Profession"
    _columns = {
        'code': fields.char('Code', size=2),
        'name': fields.char('Name', size=64),
    }
    
    def sync(self, cr, uid, eib_db):
        
        sql = "SELECT codice, denominazione_it FROM PAR_PROFESSIONE "
        cursor = eib_db.cursor()
        cursor.execute(sql)
        for element in cursor.fetchall():
            # Execute sync
            vals = {
                'code': element[0],
                'name': element[1],
                }
            domain = [('code', '=', element[0])]
            el_ids = self.search(cr, uid, domain)
            if el_ids:
                self.write(cr, uid, el_ids, vals)
            else:
                el_id = self.create(cr, uid, vals)
                
        return True
    
class eib_conn_address_type(orm.Model):
    
    _name = "eib.conn.address.type"
    _description = "EIB connector - Address Type"
    _columns = {
        'code': fields.char('Code', size=2),
        'name': fields.char('Name', size=64),
        'main': fields.boolean('Main'),
        'rel_type' : fields.selection([
            ('default','Default'),
            ('invoice','Invoice'),
            ('delivery','Delivery'),
            ('contact','Contact'),
            ('other','Other'),
            ], 'Relation Type'),
    }
    
    def sync(self, cr, uid, eib_db):
        sql = "SELECT sigla, denominazione_it, ambito_indirizzo FROM TIPI_INDIRIZZI "
        cursor = eib_db.cursor()
        cursor.execute(sql)
        for element in cursor.fetchall():
            # setup main
            if not element[2]:
                setup_main = True
            else:
                setup_main = False
            # Execute sync
            vals = {
                'code': element[0],
                'name': element[1],
                'main': setup_main,
                }
            domain = [('code', '=', element[0])]
            el_ids = self.search(cr, uid, domain)
            if el_ids:
                #el_id = el_ids[0]
                self.write(cr, uid, el_ids, vals)
            else:
                el_id = self.create(cr, uid, vals)
        
        return True
