#import logging

from urllib import request
from html.parser import HTMLParser

from homeassistant.util import slugify

#_LOGGER = logging.getLogger(__name__)

HOST = 'http://wiki.9livesdata.com'

class WorktimeParser(HTMLParser):

    def __init__(self):
        HTMLParser.__init__(self)
        self._in_table = False
        self._current_row = []
        self._level = []
        self._current_cell = ''
        self.rows = []

    def handle_starttag(self, tag, attrs):
        self._level.append(tag)
        if tag == 'table':
            assert(self._in_table is False)
            self._in_table = True
        elif self._in_table and tag == 'tr':
            self._current_row = []
        elif self._in_table and tag in ['td', 'th']:
            self._current_cell = ''
        elif self._in_table and tag == 'img':
            src_attrs = [attr for attr in attrs if attr[0] == 'src']
            if len(src_attrs) > 0 :
                self._current_cell += HOST + src_attrs[0][1]

    def handle_endtag(self, tag):
        if tag == 'table':
            assert(self._in_table is True)
            self._in_table = False
        elif self._in_table and tag == 'tr':
            self.rows.append(self._current_row)
        elif self._in_table and tag in ['td', 'th']:
            self._current_row.append(self._current_cell)
        self._level.pop()

    def handle_data(self, data):
        if self._in_table and self._level[-1] in ['td', 'th', 'a']:
            self._current_cell += data.strip()

def parse_matrix(url):
    source = request.urlopen(url).read().decode('utf-8')
    parser = WorktimeParser()
    parser.feed(source)
    return parser.rows

def consultants():
    matrix = parse_matrix('%s/wiki/index.php/Facebook' % HOST)
    header = matrix[0]
    def decode(row):
        attrs = {k: v for (k,v) in zip(header, row)}
        if '@' in attrs['EMAIL']:
            attrs['id'] = attrs['EMAIL'].split('@')[0]
        return attrs
    return {attrs['id']: attrs for attrs in [decode(row) for row in matrix[1:]] if 'id' in attrs}

def consultants_cars():
    matrix = parse_matrix('%s/wiki/index.php/Carbook' % HOST)
    header = matrix[0]
    def decode(row):
        attrs = {k: v for (k,v) in zip(header, row)}
        attrs['id'] = slugify("%s_%s_%s" % (attrs['CONSULTANT'], attrs['MODEL'], attrs['PLATE']))
        attrs['PIC'] = "http://logo.clearbit.com/%s.com" % attrs['MARK']
        return attrs
    return {attrs['id']: attrs for attrs in [decode(row) for row in matrix[1:]] if 'id' in attrs}
