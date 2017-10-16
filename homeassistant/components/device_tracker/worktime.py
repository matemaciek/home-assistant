import collections
import logging
import urllib
import random

from homeassistant.components.device_tracker import (DEFAULT_SCAN_INTERVAL)
from homeassistant.helpers.event import track_point_in_utc_time
from homeassistant.util import slugify
from homeassistant import util
from homeassistant.util.worktime import consultants, consultants_cars

_LOGGER = logging.getLogger(__name__)


class Host(object):

    def __init__(self, login, hass, facebook_data):
        self.hass = hass
        self.login = login
        self.dev_id = login
        self.facebook_data = facebook_data
        self.is_in = False
        self.at_work = False
        self.human = True

    def _offset(self):
        return (random.random() - 0.5)/400

    def check(self, wt):
        return wt == 'at work' or wt == 'on break'

    def work(self, wt):
        return wt == 'at work'

    def on_break(self, wt):
        return wt == 'on break'

    def update(self, see, wt):
        data = {k: v for k, v in self.facebook_data.items() if k != 'PIC'}
        self.is_in = self.check(wt)
        self.at_work = self.work(wt)
        data['human'] = self.human
        data['in'] = self.is_in
        data['break'] = self.on_break(wt)
        data['work'] = self.at_work
        data['friendly_name'] = self.facebook_data['CONSULTANT']
        see(dev_id=self.dev_id, gps=None, source_type='work_time', location_name=wt, picture=self.facebook_data['PIC'], attributes=data)
        if self.check(wt):
            return True


class CarHost(object):

    def __init__(self, login, hass, facebook_data):
        self.hass = hass
        self.login = login
        self.dev_id = login
        self.facebook_data = facebook_data
        self.human = False
        try:
            self.p = float(facebook_data['PROBABILITY'])
        except ValueError:
            self.p = 0.0

    def check(self, wt):
        return wt == 'at work' or wt == 'on break'

    def work(self, wt):
        return wt == 'at work'

    def on_break(self, wt):
        return wt == 'on break'

    def update(self, see, wt):
        data = {k: v for k, v in self.facebook_data.items() if k != 'PIC'}
        self.is_in = self.check(wt)
        self.at_work = self.work(wt)
        data['human'] = self.human
        data['friendly_name'] = "%s %s %s %s" % (self.facebook_data['MARK'], self.facebook_data['MODEL'], self.facebook_data['COLOUR'], self.facebook_data['PLATE'])
        see(dev_id=self.dev_id, gps=None, source_type='work_time', location_name=wt, picture=self.facebook_data['PIC'], attributes=data)
        if self.check(wt):
            return True


def setup_scanner(hass, config, see, discovery_info=None):
    all_consultants = consultants()
    all_cars = consultants_cars()
    project_key = 'PROJECT'
    team_key = 'TEAM'
    order_offset = 1000
    d = collections.defaultdict(list)
    rooms = collections.defaultdict(list)
    for consultant in all_consultants.values():
        d[consultant[project_key]].append(consultant)
        rooms[consultant['ROOM']].append(consultant['id'])

    current_order_offset = order_offset + 1
    for k in sorted(d.keys()):
        if k != '':
            project_consultants = d[k]
            hass.states.set('group.p_%s' % slugify(k), len(project_consultants), {'unit_of_measurement': 'human', 'friendly_name': k, 'entity_id': sorted(['device_tracker.%s' % c['id'] for c in project_consultants])})
            teams = collections.defaultdict(list)
            for consultant in project_consultants:
                teams[consultant[team_key]].append(consultant['id'])
                hass.states.set('sensor.room_%s' % slugify(consultant['ROOM']), 0, {'unit_of_measurement': 'human'})
            for team in sorted(teams.keys()):
                hass.states.set('group.t_%s_%s' % (slugify(k), slugify(team)), len(teams[team]), {'unit_of_measurement': 'human', 'friendly_name': team, 'entity_id': ['device_tracker.%s' % c for c in sorted(teams[team])]})
            hass.states.set('group.%s' % slugify(k), 'off', {'order': current_order_offset, 'view':'yes', 'friendly_name': k, 'entity_id': ['group.t_%s_%s' % (slugify(k), slugify(team)) for team in sorted(teams.keys())]})
            current_order_offset += 1

    hass.states.set('group.9livesdata', 'off', {'order': order_offset, 'view':'yes', 'friendly_name': '9LivesData', 'entity_id': ['group.p_%s' % slugify(project) for project in sorted(d.keys())]})

    hass.states.set('group.rooms', 'off', {'order': current_order_offset, 'view':'yes', 'friendly_name': 'Rooms', 'entity_id': ['group.room_%s' % slugify(room) for room in sorted(rooms.keys())]})
    for room in rooms.keys():
        hass.states.set('group.room_%s' % slugify(room), len(rooms[room]), {'unit_of_measurement': 'human', 'friendly_name': room, 'entity_id': ['device_tracker.%s' % c for c in rooms[room]]})

    hass.states.set('group.cars2', len(all_cars), {'friendly_name': 'All cars', 'entity_id': ['device_tracker.%s' % car for car in all_cars]})

    hosts = {login: Host(login, hass, facebook_data) for (login, facebook_data) in all_consultants.items()}
    cars_hosts = [CarHost(id, hass, carbook_data) for (id, carbook_data) in all_cars.items()]

    def update_state(id, state):
        old_attr = hass.states.get(id).attributes
        hass.states.set(id, state, old_attr)

    def _get_states():
        url = 'http://toolbox:8998/WorkTime/json?userName=sokolowski&action=GETATTENDANCE'
        rows = urllib.request.urlopen(url).readlines()
        decoded_rows = [row.decode('ISO-8859-2').strip().split(',') for row in rows]

        def good(row):
            return len(row[0]) > 0 and len(row) >= 4
        return {row[0]: row[3] for row in decoded_rows if good(row)}

    interval = DEFAULT_SCAN_INTERVAL
    _LOGGER.info("Started worktime tracker with interval=%s", interval)

    def update(now):
        states = _get_states()
        rooms = collections.defaultdict(list)
        projects = collections.defaultdict(list)
        teams = collections.defaultdict(list)
        cars = 0.0
        cars_max = 0
        cars_present = []

        def state(login):
            return states.get(login) if login in states else 'out of office'

        for host in hosts.values():
            host.update(see, state(host.login))
            rooms[slugify(host.facebook_data["ROOM"])].append(host)
            projects[slugify(host.facebook_data[project_key])].append(host)
            teams[slugify("%s_%s" % (host.facebook_data[project_key], host.facebook_data[team_key]))].append(host)
            owned_cars = [car for car in cars_hosts if car.facebook_data['CONSULTANT'] == host.login and car.p > 0]
            if len(owned_cars) > 0 and host.is_in:
                cars_max += 1

        for car in cars_hosts:
            owner_id = car.facebook_data['CONSULTANT']
            owner = hosts[owner_id]
            if owner.is_in and car.p > 0:
                cars += car.p
                cars_present.append(car.login)
            owner_phone = all_consultants[owner_id]['PHONE']
            car.update(see, owner_phone if len(owner_phone) > 0 else "Missing!")

        for room in rooms:
            update_state('sensor.room_%s' % room, sum([host.is_in for host in rooms[room]]))
            update_state('group.room_%s' % room, sum([host.at_work for host in rooms[room]]))
        for project in projects:
            update_state('group.p_%s' % project, sum([host.at_work for host in projects[project]]))
        for team in teams:
            update_state('group.t_%s' % team, sum([host.at_work for host in teams[team]]))
        hass.states.set('group.cars', cars, {'unit_of_measurement': 'car', 'friendly_name': 'Cars in', 'entity_id': ['device_tracker.%s' % c for c in cars_present]})
        hass.states.set('sensor.cars_max', cars_max, {'unit_of_measurement': 'car', 'friendly_name': 'at parking high estimation'})

        track_point_in_utc_time(hass, update, util.dt.utcnow() + interval)
        return True

    return update(util.dt.utcnow())
