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

import argparse
import json
import os
from pprint import pprint
import subprocess
import sys

from lib import Flow


OVS_OFCTL = '/usr/bin/ovs-ofctl'


def parse_args():
    parser = argparse.ArgumentParser(description='openflow parser')
    parser.add_argument('--disable-unicode', action='store_true',
                        help='do not output unicode characters')
    parser.add_argument('--json', action='store_true',
                        help='output json format')
    parser.add_argument('--show-config', action='store_true',
                        help='display the specified flozer args/config')
    parser.add_argument('--conf', metavar='config file',
                        default='~/.flozer.json',
                        help='config file if not ~/.flozer')
    parser.add_argument('-O', '--protocol', metavar='OpenFlow protocol',
                        help='openflow protocol to use for collecting flows, '
                             'see the ovs-ofctl man page for more info. '
                             'flozer defaults to OpenFlow13')
    parser.add_argument('bridges', nargs='*', action='store',
                        help='bridge to dump flows on')
    return parser.parse_args()


def parse_config(conf_file):
    try:
        with open(os.path.expanduser(conf_file)) as f:
            config = json.load(f)
    except IOError:
        return {}

    # cookie map is a function so the string needs to be converted
    if 'cookie_map' in config:
        # get ready for some srs business
        f = compile(config['cookie_map'], conf_file, 'eval')
        config['cookie_map'] = eval(f, {'__builtins__': {}})

    # integerize the tables
    if 'table_map' in config:
        config['table_map'] = {int(k): v
                               for k, v in config['table_map'].iteritems()}
    # parse json for boolean
    if 'json' in config:
        if config['json'] in ('true', 'True', 'yes', 'Yes', '1', 1):
            config['json'] = True
        else:
            config['json'] = False

    # parse disable_unicode for boolean
    if 'disable_unicode' in config:
        if config['disable_unicode'] in ('true', 'True', 'yes', 'Yes', '1', 1):
            config['disable_unicode'] = True
        else:
            config['disable_unicode'] = False

    return config


def get_stdin():
    stdin_lines = []
    for line in sys.stdin:
        stdin_lines.append(line)
    return stdin_lines


def collect_flows(bridges, protocol):
    flows = []
    for bridge in bridges:
        args = [OVS_OFCTL, 'dump-flows', '-O', protocol, bridge]
        flows.append(subprocess.check_output(args).split('\n'))
    return flows


def execute():
    args = parse_args()
    conf = parse_config(args.conf)

    # merge args and conf preferring args over conf values
    # also set a few defaults
    disable_unicode = (args.disable_unicode or
                       conf.get('disable_unicode', False))
    json_output = args.json or conf.get('json', False)
    protocol = args.protocol or conf.get('protocol', 'OpenFlow13')

    if args.show_config:
        print 'bridges: %s' % args.bridges
        print 'OpenFlow protocol used: %s' % protocol
        print 'json output: %s' % json_output
        print 'disable unicode: %s' % disable_unicode
        print 'conf file: %s' % args.conf
        print 'conf file contents:'
        pprint(conf)
        return

    # collect raw flows
    if not args.bridges:
        flows = get_stdin()
    else:
        # default to OpenFlow13 if not specified in args or conf
        flows = collect_flows(args.bridges, protocol)

    # parse flows
    kwargs = {'cookie_map': conf.get('cookie_map'),
              'match_map': conf.get('match_map'),
              'table_map': conf.get('table_map'),
              'action_map': conf.get('action_map'),
              'disable_unicode': disable_unicode}
    flows = [Flow(flow, **kwargs) for flow in flows
             if flow and '_FLOW reply' not in flow]

    # output flows
    if json_output:
        print json.dumps(flows)
    else:
        for flow in flows:
            print flow
            print


if __name__ == '__main__':
    execute()
