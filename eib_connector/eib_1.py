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

class eib_conn_log_move(orm.Model):
    
    _name = "eib.conn.log.move"
    _description = "EIB connector - Log move"
    _columns = {
        'date': fields.date('Date', readonly=True),
        'partner_line_ids': fields.one2many('eib.conn.log.partner', 'move_id', 'Partner Lines', readonly=True),
    }
    
    def execute_sync(self, cr, uid, params, context=None):
        
        '''
        nuovo ip 89.190.175.41<<<
        vecchio ip 217.199.6.150<<<
        try:
            dsn = cx_Oracle.makedsn("89.190.175.41", 1521, "xe")
            db = cx_Oracle.connect("EIBGWT", "EIBGWT", dsn)
            
        except cx_Oracle.DatabaseError, exc:
            error, = exc.args
            print 'sono in errore %s'%(error)
        '''
        # Test REST
        #service_base_url = 'https://www.edp-progetti.it/eibmanager/ws/'
        #service_function_url = 'anagrafiche/getContraente'
        #url = service_base_url + service_function_url
        url = 'https://eibbstudio.edp-progetti.it/eibbstudio/ws/anagrafiche/getContraente/1'
        
        #authKey = base64.b64encode("acamilli:alca74")
        authKey = base64.b64encode("wsuser:pwws2014")
        headers = {"Content-Type":"application/json", "Authorization":"Basic " + authKey}
        data = {'contrId': 1}
        import pdb
        pdb.set_trace()
        request = urllib2.Request(url)
        
        for key,value in headers.items():
            request.add_header(key,value)
            
        response = urllib2.urlopen(request)
        result = response.read()
        contraente = json.loads(result)
        
        # Test REST COMPAGNIA
        url = 'https://eibbstudio.edp-progetti.it/eibbstudio/ws/anagrafiche/listCompagnia'
        data = {"from_id" : 1, "to_id": 9999999, "codfisc": "", "ragsoc": ""}
        data_json = json.dumps(data)
        headers = {"Content-Type":"application/x-www-form-urlencoded", "Authorization":"Basic " + authKey}
        import pdb
        pdb.set_trace()
        request_object = urllib2.Request(url, data_json)
        #request_object = urllib2.Request(url)
        for key,value in headers.items():
            request_object.add_header(key,value)
        response = urllib2.urlopen(request_object)
        
        #request = urllib2.Request(url)
        #response = urllib2.urlopen(request)
        #result = response.read()
        #compagnie = json.loads(result)
        
        # Soggetti
        
        # ... Controls
        soggetti_to_import = []
        soggetti_to_import_already_exist = []
        sql = "SELECT * FROM ANAGRAFICHE_SOGGETTI"
        cursor = db.cursor()
        cursor.execute(sql)
        #for line in cursor.fetchall():
        for line in cursor:
            val = {
                'id' : line[0],
                'attivo' : line[1],
                'ragione_sociale' : line[2],
                'codice_fiscale' : line[6],
                'partita_iva' : line[7],
                'data_nascita' : line[8],
                'sesso' : line[9],
                'note' : line[10],
                'persona' : line[11],
                'stato_civile' : line[12],
                'tipo_invio_documenti' : line[14],
                }
            soggetti_to_import.append(val)
        
        # ... Sync
        for element_to_import in soggetti_to_import:
            self.sync_soggetto(cr, uid, element_to_import, None, params, context)
            
        
        return True
    
    def sync_soggetto(self, cr, uid, element_to_import, element_to_export, params, context=None):
        
        def _set_OE_values(element_to_import):
            # setup P.IVA
            if element_to_import['partita_iva']:
                p_iva = '{:11s}'.format(element_to_import['partita_iva'].zfill(11)) 
                setup_vat = 'IT' + p_iva #<<< da impostare in base al codice stato
            OE_element = {
                    'is_company' : True,
                    #'ref' : element_to_import['ref'],
                    'name' : element_to_import['ragione_sociale'],
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
                    'fiscalcode' : element_to_import['codice_fiscale'],
                    }
            return OE_element
         
        rel_partner_obj = self.pool['eib.conn.rel.partner']
        import pdb
        pdb.set_trace()
        # Import
        if element_to_import:
            partnerOE = _set_OE_values(element_to_import)
            
            # If exist
            domain = [('eib_partner_id', '=', element_to_import_id)] 
            rel_partner_ids = rel_partner_obj.search(cr, uid, domain)
        
        
        
        return True
    
class eib_conn_log_partner(orm.Model):
    
    _name = "eib.conn.log.partner"
    _description = "EIB connector - Log partner"
    _columns = {
        'date': fields.date('Date'),
        'move_id': fields.many2one('eib.conn.log.move', 'Move Ref', readonly=True, ondelete='cascade'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True),
        'description': fields.text('Description'),
    }
    
class eib_conn_rel_partner(orm.Model):
    
    _name = "eib.conn.rel.partner"
    _description = "EIB connector - Rel Partner"
    _columns = {
        'eib_partner_id': fields.integer('EIB partner id'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True),
    }