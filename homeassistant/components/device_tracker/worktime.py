import collections
import logging
import urllib
import random

from homeassistant.components.device_tracker import (
    DEFAULT_SCAN_INTERVAL, SOURCE_TYPE_ROUTER)
from homeassistant.helpers.event import track_point_in_utc_time
from homeassistant.util import slugify
from homeassistant import util
from homeassistant.util.worktime import consultants

_LOGGER = logging.getLogger(__name__)


class Host(object):

    def __init__(self, login, dev_id, hass, facebook_data):
        self.hass = hass
        self.login = login
        self.dev_id = dev_id
        self.facebook_data = facebook_data

    def _offset(self):
        return (random.random() - 0.5)/400

    def check(self, wt):
        return wt == 'at work'

    def update(self, see, wt):
        see(dev_id=self.dev_id, gps=None, source_type='work_time', location_name=wt, picture=self.facebook_data['PIC'], attributes={k: v for k, v in self.facebook_data.items() if k != 'PIC'})
        if self.check(wt):
            return True


def setup_scanner(hass, config, see, discovery_info=None):
    all_consultants = consultants()
    project_key = 'PROJECT'
    team_key = 'TEAM'
    order_offset = 1000
    d = collections.defaultdict(list)
    for consultant in all_consultants.values():
        d[consultant[project_key]].append(consultant)

    current_order_offset = order_offset + 1
    for k in sorted(d.keys()):
        if k != '':
            project_consultants = d[k]
            hass.states.set('group.p_%s' % slugify(k), 'off', {'friendly_name': k, 'entity_id': sorted(['device_tracker.%s' % c['id'] for c in project_consultants])})
            teams = collections.defaultdict(list)
            for consultant in project_consultants:
                teams[consultant[team_key]].append(consultant['id'])
            for team in sorted(teams.keys()):
                hass.states.set('group.t_%s_%s' % (slugify(k), slugify(team)), 'off', {'friendly_name': team, 'entity_id': ['device_tracker.%s' % c for c in sorted(teams[team])]})
            hass.states.set('group.%s' % slugify(k), 'off', {'order': current_order_offset, 'view':'yes', 'friendly_name': k, 'entity_id': ['group.t_%s_%s' % (slugify(k), slugify(team)) for team in sorted(teams.keys())]})
            current_order_offset += 1
    hass.states.set('group.9livesdata', 'off', {'order': order_offset, 'view':'yes', 'friendly_name': '9LivesData', 'entity_id': ['group.p_%s' % slugify(project) for project in sorted(d.keys())]})

    #group = slugify(facebook_data['TEAM'])
    #hass.states.set('group.%s' % group, 'off', {'entity_id': ['device_tracker.%s' % login], 'name': facebook_data['TEAM']})

    hosts = [Host(login, login, hass, facebook_data) for (login, facebook_data) in all_consultants.items()]


    #hass.states.set('group.9LivesData', 'off', {'entity_id': ['device_tracker.%s' % c for c in all_consultants.keys()]})

    def _get_states():
        url = 'http://toolbox:8998/WorkTime/json?userName=sokolowski&action=GETATTENDANCE'
        rows = urllib.request.urlopen(url).readlines()
        decoded_rows = [row.decode('ascii').strip().split(',') for row in rows]
        return  {row[0]: row[3] for row in decoded_rows if len(row[0]) > 0}

    interval = DEFAULT_SCAN_INTERVAL
    _LOGGER.info("Started worktime tracker with interval=%s", interval)

    def update(now):
        states = _get_states()
        for host in hosts:
            host.update(see, states.get(host.login) if host.login in states else 'out of oifice')
        track_point_in_utc_time(hass, update, util.dt.utcnow() + interval)
        return True

    return update(util.dt.utcnow())
