# -*- coding: utf-8 -*-
###################################################################################
#
#    ALTANMYA - TECHNOLOGY SOLUTIONS
#    Copyright (C) 2022-TODAY ALTANMYA - TECHNOLOGY SOLUTIONS Part of ALTANMYA GROUP.
#    ALTANMYA Parallel and sequential Approvals and Status
#    Author: ALTANMYA for Technology(<https://tech.altanmya.net>)
#
#    This program is Licensed software: you can not modify
#   #
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################
{
    'name': 'MCGI-Purchase Order Extension',
    'version': '1.0',
    'summary': 'Parallel and sequential Approvals and Status',
    'description': "Parallel and sequential Approvals and Status",
    'category': 'Inventory/Purchase',
    'author': 'ALTANMYA - TECHNOLOGY SOLUTIONS',
    'company': 'ALTANMYA - TECHNOLOGY SOLUTIONS Part of ALTANMYA GROUP',
    'website': "https://tech.altanmya.net",
    'post_init_hook': 'test_post_init_hook',
    'depends': ['purchase'],
    'data': ['security/ir.model.access.csv','security/security.xml','views/view_actions.xml','views/view_menu.xml','views/view_pages.xml'],
    'demo': [],
    'qweb': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}
