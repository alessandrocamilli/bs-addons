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

from osv import fields,orm, osv
from tools.translate import _
import time 

class wizard_sync(osv.osv_memory):
    
    def default_get(self, cr, uid, fields, context=None):
        res = super(wizard_sync, self).default_get(cr, uid, fields, context=context)
        #res['anno'] = int(time.strftime('%Y')) -1
        return res

    _name = "eib.conn.wizard.sync"
    _columns = {
    }
    
    def execute_sync(self, cr, uid, ids, context=None):
        
        eib_move_obj = self.pool['eib.conn.log.move']
        wizard = self.read(cr, uid, ids)[0]
        
        #quadri_richiesti = []
        #if wizard['quadro_FA']:
        #    quadri_richiesti.append('FA')
        
        params ={
               #'company_id': wizard['company_id'][0],
               }
        eib_move_obj.execute_sync(cr, uid, params, context=None)
        
        return {
            'type': 'ir.actions.act_window_close',
        }
