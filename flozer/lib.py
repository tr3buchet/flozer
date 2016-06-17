#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2016 Trey Morris
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#


class Fields(tuple):
    def __new__(cls, s, elements):
        return super(Fields, cls).__new__(cls, elements)

    def __init__(self, s, elements):
        self._string = s
        self._mapped_string = None

    @property
    def string(self):
        return self._string

    @property
    def mstring(self):
        if self._mapped_string is not None:
            return self._mapped_string

        self._mapped_string = ','.join([m.mstring for m in self])
        return self._mapped_string

    def __contains__(self, s):
        return s in self.string or s in self.mstring

    def get(self, s):
        return [m for m in self if m.name == s or m.mname == s]

    def __unicode__(self):
        return ', '.join(str(match) for match in self)

    def __str__(self):
        return unicode(self).encode('utf-8')


class Field(dict):
    def __init__(self, s, item_map=None, table_map=None):
        v = s.find(self.sep)
        if v != -1:
            self.name = s[:v]
            self.value = s[v + 1:]
        else:
            self.name = s
            self.value = None

        self._item_map = item_map
        self._table_map = table_map

        self._string = s
        self._mapped_string = None

        # NOTE(tr3buchet): and check out how this line makes json work!
        dict.__setitem__(self, self.mname, self.mvalue)


    @property
    def string(self):
        return self._string

    @property
    def mstring(self):
        if self._mapped_string:
            return self._mapped_string
        return self._mstring()

    def _mstring(self):
        raise NotImplemented('_mstring() needs to be defined in subclass')

    @property
    def mname(self):
        v = self.mstring.find(self.sep)
        if v != -1:
            return self.mstring[:v]
        return self.mstring

    @property
    def mvalue(self):
        v = self.mstring.find(self.sep)
        if v != -1:
            return self.mstring[v + 1:]
        return None

    def __unicode__(self):
        return self.mname + '(' + (self.mvalue or '') + ')'

    def __str__(self):
        return unicode(self).encode('utf-8')

    # NOTE(tr3buchet): make these read only!
    def __setitem__(self, *args, **kwargs):
        raise Exception('Field is read only')

    def __delitem__(self, *args, **kwargs):
        raise Exception('Field is read only')

    def clear(self, *args, **kwargs):
        raise Exception('Field is read only')

    def pop(self, *args, **kwargs):
        raise Exception('Field is read only')

    def popitem(self, *args, **kwargs):
        raise Exception('Field is read only')

    def setdefault(self, *args, **kwargs):
        raise Exception('Field is read only')

    def update(self, *args, **kwargs):
        raise Exception('Field is read only')

    def copy(self, *args, **kwargs):
        raise Exception('Field is read only')


class Action(Field):
    sep = ':'

    def _mstring(self):
        ms = self.string
        if self._item_map:
            if 'resubmit(,' in self._item_map and 'resubmit(,' in ms:
                ms = self._item_map['resubmit(,'] + self.sep + ms[10:-1]
            for k, v in self._item_map.iteritems():
                ms = ms.replace(k, v)

        if self._table_map and 'goto_table' in ms:
            ms = 'goto_table:' + self._table_map[int(ms.split(self.sep)[1])]

        self._mapped_string = ms
        return self._mapped_string


class Match(Field):
    sep = '='

    def _mstring(self):
        ms = self.string
        if self._item_map:
            for k, v in self._item_map.iteritems():
                ms = ms.replace(k, v)

        self._mapped_string = ms
        return self._mapped_string


class Flow(dict):
    def __init__(self, flow_string, cookie_map=None, table_map=None,
                 match_map=None, action_map=None, disable_unicode=False):
        self._string = flow_string.strip()
        self.disable_unicode = disable_unicode

        # maps for things found in flows
        # cookie_map is a function that will be executed against each cookie
        self.cookie_map = cookie_map
        # table_map is a dictionary of maps from int table-id to a string
        # table_map applies to flow's table and any goto_table or resubmits
        self.table_map = table_map
        # match_map and action_map are dicts of str replacements for matches
        # and for actions, string substitutions are performed
        self.match_map = match_map or {}
        self.action_map = action_map or {}

        # useful variables for things that have been mapped
        # for example once your table has been mapped to some string
        # you can still use self.raw_table to get the integer table
        self.table = None
        self.label = '--'

        try:
            # split everything up into sections, moving priority out of matches
            tokens = self.string.split(', ')
            match_action = tokens.pop()
            match_string, action_string = match_action.split(' actions=')
            priority, match_string = self._extract_priority(match_string)
            tokens.append(priority)

            # parse fields
            self['fields'] = self._parse_fields(tokens)

            # parse matches and actions
            self['matches'] = self._get_matches(match_string)
            self['actions'] = self._get_actions(action_string)
        except:
            # TODO(tr3buchet): proper LOG
            print 'error processing flow |%s|' % self.string
            raise

    @property
    def string(self):
        return self._string

    def fget(self, field, default=None):
        return self['fields'].get(field, default)

    def aget(self, field, default=None):
        return self['actions'].get(field, default)

    def mget(self, field, default=None):
        return self['matches'].get(field, default)

    @staticmethod
    def _extract_priority(match_string):
        i = match_string.find('priority')
        if i != -1:
            j = match_string.find(',', i)
            if j != -1:
                # not the end
                priority = match_string[i:j]
            else:
                # the end
                priority = match_string[i:]
            new_ms = ','.join([s for s in match_string.split(',')
                               if 'priority' not in s])
        else:
            priority = 'priority=' + str(0x8000)
            new_ms = match_string

        return priority, new_ms

    def _parse_fields(self, tokens):
        fields = {}
        for token in tokens:
            k, v = token.split('=')
            fields[k] = v

        if 'table' in fields:
            self.table = int(fields['table'])
            if self.table_map:
                fields['table'] = self.table_map[self.table]
            else:
                fields['table'] = self.table

        fields['priority'] = int(fields['priority'])

        if self.cookie_map:
            self.label = self.cookie_map(int(fields['cookie'], 16))

        return fields

    def _get_actions(self, action_string):
        astrings = []
        tokens = action_string.split(',')
        i = 0
        while i < len(tokens):
            supertoken = tokens[i]
            if 'resubmit' in tokens[i]:
                supertoken = tokens[i] + ',' + tokens[i + 1]
                i += 1
            astrings.append(supertoken)
            i += 1
        A = lambda token: Action(token, self.action_map, self.table_map)
        return Fields(action_string, (A(astring) for astring in astrings
                                      if astring))

    def _get_matches(self, match_string):
        mstrings = match_string.split(',')
        M = lambda token: Match(token, self.match_map, self.table_map)
        return Fields(match_string, (M(mstring) for mstring in mstrings
                                     if mstring))

#    def _parse_actions(self, action_string):
#        # replace resubmits with openflow 1.3 goto_table
#        i = action_string.find('resubmit(,')
#        while i != -1:
#            j = action_string.find(')', i)
#            action_string = (action_string[:i] + 'goto_table:' +
#                             action_string[i + 10:j] + action_string[j + 1:])
#            i = action_string.find('resubmit(,')
#
#        # apply action_map
#        for k, v in self.action_map.iteritems():
#            action_string = action_string.replace(k, v)
#
#        actions = []
#        for action in action_string.split(','):
#            # handle goto_table mapping
#            if 'goto_table' in action and self.table_map:
#                action = ('goto_table:' +
#                          self.table_map[int(action.split(':')[1])])
#
#            actions.append(action)
#
#        return actions
#
#    def _parse_matches(self, match_string):
#        # apply match_map
#        for k, v in self.match_map.iteritems():
#            match_string = match_string.replace(k, v)
#
#        matches = {}
#        for match in match_string.split(','):
#            match = match.split('=')
#            matches[match[0]], = match[1:] or [None]
#
#        # i don't like priority being in matches, move it to primary fields
#        if 'priority' in matches:
#            self.fields['priority'] = int(matches['priority'])
#            del matches['priority']
#        else:
#            self.fields['priority'] = 0x8000
#
#        return matches

    def _match_str(self):
        s = ''
        for k, v in self['matches'].iteritems():
            if v:
                s += k + '=' + v + ', '
            else:
                s += k + ', '
        s = s[:-2]
        return s

    def __lt__(self, other_bro):
        return self['fields']['priority'] < other_bro['fields']['priority']

    def __unicode__(self):
        s = ('%(label)s cookie=%(cookie)s table=%(table)s '
             'priority=%(priority)s n_packets=%(n_packets)s\n')
        if self.disable_unicode:
            s += (' -> matches | %(matches)s\n'
                  ' -> actions | %(actions)s\n')
        else:
            s += (u' ⤷ matches │ %(matches)s\n'
                  u' ⤷ actions │ %(actions)s\n')
        values = {'label': self.label,
                  'cookie': self.fget('cookie'),
                  'table': self.fget('table'),
                  'priority': self.fget('priority'),
                  'n_packets': self.fget('n_packets'),
                  'matches': self['matches'],
                  'actions': self['actions']}

        return s % values

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __repr__(self):
        return 'Flow(%r)' % self.string
