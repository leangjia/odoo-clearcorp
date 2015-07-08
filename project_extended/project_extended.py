# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Addons modules by CLEARCORP S.A.
#    Copyright (C) 2009-TODAY CLEARCORP S.A. (<http://clearcorp.co.cr>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp.osv import osv, fields
from dateutil.relativedelta import relativedelta
from datetime import datetime

_TASK_STATE = [('draft', 'New'), ('open', 'In Progress'), ('pending', 'Pending'), ('done', 'Done'), ('cancelled', 'Cancelled')]

class project_task_type(osv.Model):
    
    _inherit = 'project.task.type'

    _columns = {
        'state': fields.selection(_TASK_STATE, 'Related Status', required=True),
        'task_type':fields.many2one('task.type', string='Task Type'),
    }
    
    def mark_done(self, cr, uid, ids, context=None):
        values = {
            'state': 'done',
            'name': _('Done'),
            'readonly':'True',
        }
        self.write(cr, uid, ids, values, context=context)
        return True

    _defaults = {
        'state': 'open',
        'fold': False,
        'case_default': False,
     }
    

class project(osv.Model):
    _inherit = 'project.project'
    
    def name_get(self, cr, uid, ids=[], context=None):
        res = []
        if isinstance(ids, int):
            ids = [ids]
        for project in self.browse(cr, uid, ids, context=context):
            data = []
            proj = project.parent_id
            while proj and proj.parent_id:
                if proj.code != '' and proj.code != False:
                    data.insert(0, (proj.code))
                    proj = proj.parent_id
                    continue
                else:
                    data.insert(0, (proj.name))
                    proj = proj.parent_id
            data.append(project.name)
            data = ' / '.join(data)
            res.append((project.id, data))
        return res

    def _shortcut_name(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        for m in self.browse(cr, uid, ids, context=context):
            res = self.name_get(cr, uid, ids)
            return dict(res)
        return res

    _columns = {
        'shortcut_name':        fields.function(_shortcut_name, method=True, store=True, string='Project Name', type='char', size=350),
        'ir_sequence_id':       fields.many2one('ir.sequence', 'Sequence'),
        
    }

    def create(self, cr, uid, vals, context=None):
        ir_sequence_obj = self.pool.get('ir.sequence')        
        project_id = super(project, self).create(cr, uid, vals, context)
        shortcut_name_dict = self._shortcut_name(cr, uid, [project_id], None, None)
        sequence_name = "Project_" + str(project_id) + " " + shortcut_name_dict[project_id]
        ir_sequence_id = ir_sequence_obj.create(cr, uid, {'name': sequence_name}, context)
        self.write(cr, uid, project_id, {'ir_sequence_id': ir_sequence_id }, context)
        return project_id
    
    def unlink(self, cr, uid, ids, context=None):
        ir_sequence_ids = []
        ir_sequence_obj = self.pool.get('ir.sequence')       
        for proj in self.browse(cr, uid, ids, context=context):
            if proj.ir_sequence_id:
                ir_sequence_ids.append(proj.ir_sequence_id.id)
        res = super(project, self).unlink(cr, uid, ids, context=context)
        ir_sequence_obj.unlink(cr, uid, ir_sequence_ids, context=context)
        return res
    
    def name_search(self, cr, uid, name='', args=None, operator='ilike', context=None, limit=50):
        ids = []
        
        if name:
            ids = self.search(cr, uid,
                              ['|', ('shortcut_name', operator, name),
                               '|', ('name', operator, name),
                               ('code', operator, name)] + args,
                              limit=limit, context=context)
        else:
            ids = self.search(cr, uid, args, limit=limit, context=context)
        
        return self.name_get(cr, uid, ids, context=context)

class task(osv.Model):
    _inherit = 'project.task'

    def _get_color_code(self, date_start, date_deadline, planned_hours, state):
        """Calculate the current color code for the task depending on the state
        Colors:
        0 -> White          5 -> Aqua
        1 -> Dark Gray      6 -> Light Aqua
        2 -> Red            7 -> Blue
        3 -> Orange         8 -> Purple
        4 -> Green          9 -> Pink
        @param self: The object pointer.
        @param date_start: The string initial date
        @param date_deadline: The string dateline
        @param planned_hours: Total planned hours for the task
        @param state: The current task state
        @return: An integer that represents the current task state as a color
        """
        if state == 'done':
            # Done task COLOR: GRAY
            return '1'
        else:
            if date_deadline:
                if date_start:
                    if planned_hours:
                        date_start = datetime.strptime(date_start, '%Y-%m-%d %H:%M:%S')
                        date_deadline = datetime.strptime(date_deadline, '%Y-%m-%d')
                        total_time_delta = relativedelta(date_deadline, date_start)
                        left_hours_delta = relativedelta(date_deadline, datetime.today())
                        total_time = (total_time_delta.days * 24) + total_time_delta.hours + (total_time_delta.minutes / 60)
                        left_hours = (left_hours_delta.days * 24) + left_hours_delta.hours + (left_hours_delta.minutes / 60)
                        percentage_left = float(left_hours) / float(total_time)
                        if percentage_left >= 0.70:
                            # COLOR: BLUE
                            return '7'
                        elif percentage_left >= 0.50:
                            # COLOR: GREEN
                            return '4'
                        elif percentage_left >= 0.30:
                            # COLOR: ORANGE
                            return '3'
                        else:
                            # COLOR: RED
                            return '2'
                        # COLOR: PINK
                        return '9'
                    else:
                        # Not planned hours available COLOR: PURPLE
                        return '8'
                else:
                    # No date_start COLOR: AQUA
                    return '6'
            else:
                # No deadline available COLOR: WHITE
                return '0'

    def _compute_color(self, cr, uid, ids, field_name, args, context={}):
        res = {}
        for task in self.browse(cr, uid, ids, context=context):
            res[task.id] = self._get_color_code(task.date_start, task.date_deadline, task.planned_hours, task.state)
        return res

    _columns = {
        'number': fields.char('Number', size=16),
        'project_id': fields.many2one('project.project', 'Project', required=True, ondelete='set null', select="1", track_visibility='onchange'),
        'color': fields.function(_compute_color, type='integer', string='Color Index'),
        'state': fields.related('stage_id', 'state', type="selection", store=True,
                selection=_TASK_STATE, string="Status", readonly=True, select=True),
        'kind_task_id':fields.many2one('ccorp.project.oerp.work.type','Type of task',required=True),
        }

    _defaults = {
                 'date_start' : lambda *a: datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S'),
                 }

    def get_number_sequence(self, cr, uid, project_id, context=None):
        ir_sequence_obj = self.pool.get('ir.sequence')
        project_obj = self.pool.get('project.project')
        project = project_obj.browse(cr, uid, project_id, context)
        return ir_sequence_obj.next_by_id(cr, uid, project.ir_sequence_id.id, context)

    def create(self, cr, uid, vals, context={}):
        if 'number' not in vals or vals['number'] == None or vals['number'] == '':
            vals.update({'number': self.get_number_sequence(cr, uid, vals['project_id'], context)})
        return super(task, self).create(cr, uid, vals, context)

    def write(self, cr, uid, ids, vals, context=None):
        if 'project_id' in vals:
            vals.update({'number': self.get_number_sequence(cr, uid, vals['project_id'], context)})
        return super(task, self).write(cr, uid, ids, vals, context)

    def set_kanban_state_blocked(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'kanban_state': 'blocked'}, context=context)

    def set_kanban_state_normal(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'kanban_state': 'normal'}, context=context)

    def set_kanban_state_done(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'kanban_state': 'done'}, context=context)
        return False

    def set_high_priority(self, cr, uid, ids, *args):
        """Set task priority to high
        """
        return self.write(cr, uid, ids, {'priority' : '0'})

    def set_normal_priority(self, cr, uid, ids, *args):
        """Set task priority to normal
        """
        return self.write(cr, uid, ids, {'priority' : '2'})

    def name_search(self, cr, uid, name='', args=None, operator='ilike', context=None, limit=50):
        ids = []
        
        if name:
            ids = self.search(cr, uid, [('number', operator, name)] + args,
                              limit=limit, context=context)
        else:
            ids = self.search(cr, uid, args, limit=limit, context=context)
        return self.name_get(cr, uid, ids, context=context)

class proyectCategory(osv.Model):
    _inherit = "project.category"

    _columns = {
                'tag_code': fields.char(size=10, string="Tag Code", required=True)
                }