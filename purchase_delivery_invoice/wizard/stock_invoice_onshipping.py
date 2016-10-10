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
from openerp.tools.translate import _

JOURNAL_TYPE_MAP = {
    ('outgoing', 'customer'): ['sale'],
    ('outgoing', 'supplier'): ['purchase_refund'],
    ('outgoing', 'transit'): ['sale', 'purchase_refund'],
    ('incoming', 'supplier'): ['purchase'],
    ('incoming', 'customer'): ['sale_refund'],
    ('incoming', 'transit'): ['purchase', 'sale_refund'],
}


class stock_invoice_onshipping(osv.osv_memory):

    _name = 'stock.invoice.onshipping.delivery'

    def _get_journal(self, cr, uid, context=None):
        journal_obj = self.pool.get('account.journal')
        journal_type = self._get_journal_type(cr, uid, context=context)
        journals = journal_obj.search(cr, uid, [('type', '=', journal_type)])
        return journals and journals[0] or False

    def _get_journal_type(self, cr, uid, context=None):
        if context is None:
            context = {}
        res_ids = context and context.get('active_ids', [])
        pick_obj = self.pool.get('stock.picking')
        pickings = pick_obj.browse(cr, uid, res_ids, context=context)
        pick = pickings and pickings[0]
        if not pick or not pick.move_lines:
            return 'sale'
        type = pick.picking_type_id.code
        usage = pick.move_lines[0].location_id.usage if type == 'incoming' \
            else pick.move_lines[0].location_dest_id.usage

        return JOURNAL_TYPE_MAP.get((type, usage), ['sale'])[0]

    _columns = {
        'journal_id': fields.many2one('account.journal', 'Destination Journal',
                                      required=True),
        'journal_type': fields.selection(
            [('purchase_refund', 'Refund Purchase'),
             ('purchase', 'Create Supplier Invoice'),
             ('sale_refund', 'Refund Sale'), ('sale',
             'Create Customer Invoice')], 'Journal Type', readonly=True),
        'group': fields.boolean("Group by partner"),
        'invoice_date': fields.date('Invoice Date'),
    }
    _defaults = {
        'journal_type': _get_journal_type,
        'journal_id': _get_journal,
    }

    def onchange_journal_id(self, cr, uid, ids, journal_id, context=None):
        if context is None:
            context = {}
        domain = {}
        value = {}
        active_id = context.get('active_id')
        if active_id:
            picking = self.pool['stock.picking'].browse(cr, uid, active_id,
                                                        context=context)
            type = picking.picking_type_id.code
            usage = picking.move_lines[0].location_id.usage if type == \
                'incoming' else picking.move_lines[0].location_dest_id.usage
            journal_types = JOURNAL_TYPE_MAP.get(
                (type, usage), ['sale', 'purchase', 'sale_refund',
                                'purchase_refund'])
            domain['journal_id'] = [('type', 'in', journal_types)]
        if journal_id:
            journal = self.pool['account.journal'].browse(cr, uid, journal_id,
                                                          context=context)
            value['journal_type'] = journal.type
        return {'value': value, 'domain': domain}

    def view_init(self, cr, uid, fields_list, context=None):
        if context is None:
            context = {}
        res = super(stock_invoice_onshipping, self).view_init(
            cr, uid, fields_list, context=context)
        pick_obj = self.pool.get('stock.picking')
        count = 0
        active_ids = context.get('active_ids', [])
        for pick in pick_obj.browse(cr, uid, active_ids, context=context):
            if pick.invoice_state != 'invoiced' and \
                    pick.carrier_invoice_control != '2binvoiced':
                count += 1
        if len(active_ids) == count:
            raise osv.except_osv(_('Warning!'), _(
                'None of these picking lists require invoicing.'))
        return res

    def open_invoice(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        invoice_ids = self.create_invoice(cr, uid, ids, context=context)
        if not invoice_ids:
            raise osv.except_osv(_('Error!'), _('No invoice created!'))

        data = self.browse(cr, uid, ids[0], context=context)

        action = {}

        journal2type = {'sale': 'out_invoice', 'purchase': 'in_invoice',
                        'sale_refund': 'out_refund',
                        'purchase_refund': 'in_refund'}
        inv_type = journal2type.get(data.journal_type) or 'out_invoice'
        data_pool = self.pool.get('ir.model.data')
        if inv_type == "out_invoice":
            action_id = data_pool.xmlid_to_res_id(
                cr, uid, 'account.action_invoice_tree1')
        elif inv_type == "in_invoice":
            action_id = data_pool.xmlid_to_res_id(
                cr, uid, 'account.action_invoice_tree2')
        elif inv_type == "out_refund":
            action_id = data_pool.xmlid_to_res_id(
                cr, uid, 'account.action_invoice_tree3')
        elif inv_type == "in_refund":
            action_id = data_pool.xmlid_to_res_id(
                cr, uid, 'account.action_invoice_tree4')

        if action_id:
            action_pool = self.pool['ir.actions.act_window']
            action = action_pool.read(cr, uid, action_id, context=context)
            action['domain'] = "[('id','in', ["+','.join(map(
                str, invoice_ids))+"])]"
            return action
        return True

    def create_invoice(self, cr, uid, ids, context=None):
        context = dict(context or {})
        data = self.browse(cr, uid, ids[0], context=context)
        journal2type = {'sale': 'out_invoice', 'purchase': 'in_invoice',
                        'sale_refund': 'out_refund',
                        'purchase_refund': 'in_refund'}
        context['date_inv'] = data.invoice_date
        inv_type = journal2type.get(data.journal_type) or 'out_invoice'
        context['inv_type'] = inv_type

        active_ids = context.get('active_ids', [])
        res = self.action_invoice_create_purchase_delivery(
            cr, uid, active_ids, journal_id=data.journal_id.id,
            group=data.group, type=inv_type, context=context)
        return res

    def action_invoice_create_purchase_delivery(
            self, cr, uid, ids, journal_id, group=False, type='out_invoice',
            context=None):
        """ Creates invoice based on the invoice state selected for picking.
        @param journal_id: Id of journal
        @param group: Whether to create a group invoice or not
        @param type: Type invoice to be created
        @return: Ids of created invoices for the pickings
        """
        picking_obj = self.pool.get('stock.picking')
        context = context or {}
        todo = {}
        delivery_partner = {}
        for picking in picking_obj.browse(cr, uid, ids, context=context):
            if not picking.carrier_id:
                raise Warning(_('The carrier is not set for this picking %s')
                              % picking.name)
            partner = picking.carrier_id.partner_id.id
            delivery_partner = picking.carrier_id.partner_id
            # grouping is based on the invoiced partner
            if group:
                key = partner
            else:
                key = picking.id
            for move in picking.move_lines:
                if move.invoice_state == 'invoiced':
                    if (move.state != 'cancel') and not move.scrapped:
                        todo.setdefault(key, [])
                        todo[key].append(move)
        invoices = []
        ctx = context.copy()
        ctx['partner_delivery'] = delivery_partner
        ctx['invoice_delivery'] = True
        for moves in todo.values():
            invoices += picking_obj._invoice_create_line(
                cr, uid, moves, journal_id, type, context=ctx)
        return invoices
