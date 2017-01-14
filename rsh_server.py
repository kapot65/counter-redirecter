#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 13 15:21:37 2017

@author: chernov
"""

import os
import sys
import json
import time
import asyncio
from argparse import ArgumentParser

from dftcp import DataforgeEnvelopeProtocol
from dftcp import DataforgeEnvelopeEchoClient as DFClient

cur_dir = os.path.dirname(os.path.realpath(__file__))
if not cur_dir in sys.path: sys.path.append(cur_dir)
del cur_dir

from utils.rsb_serializer import serialise_to_rsb

class RshServerProtocol(DataforgeEnvelopeProtocol):
    """
      Сервер транслирует и сниффит все сообщения 
    """
    def check_junk(self, meta):
        """
         Функция проверяет, является ли пересылаемое сообщение информационным
         
        """
        if "reply_type" in meta and meta["reply_type"] == "acquisition_status":
            return True
        elif meta == {}:
            return True
        else:
            return False
    
    def cbk(self, message, client_obj, ext_meta):
        meta = message["meta"]
        
        if "ext_meta" in meta:
            meta["ext_meta"] = {**meta["ext_meta"], **ext_meta}
        else:
            meta["ext_meta"] = ext_meta
            
        self.send_message(meta, message["data"], 
                          message["header"]["data_type"])
        
        if not self.check_junk(message["meta"]):
            client_obj.transport.close()
        
    def forward_message(self, meta, data, ext_meta={}):
        loop = asyncio.new_event_loop()
        
        callback = lambda msg, client: self.cbk(msg, client, ext_meta)
        client = lambda: DFClient(loop, meta, callback=callback, 
                                  timeout_sec=args.timeout)
        
        coro = loop.create_connection(client, args.host, args.port)
        
        loop.run_until_complete(coro)
        loop.run_forever()
        
    def process_message(self, message):
        
        meta = message['meta']
        ext_meta = {}
  
        if 'command_type' in meta and meta['command_type'] == "acquire_point":
            cur_patt = pattern
            cur_patt["aquisition_time"] = int(meta["acquisition_time"])*1000
            
            #~/qtprojects/build-LAn10-12PCI_base-Desktop-Release/Lan10-12PCI-Base out.rsb -s
            
            filename = "%s.rsb"%(time.strftime("%Y%m%d-%H%M%S"))
            ext_meta["rsb_file"] = filename
            
            with open(os.path.join(args.out_dir, filename), "w") as file:
                file.write(serialise_to_rsb(cur_patt))
        
        self.forward_message(meta, message['data'], ext_meta)
    
                        
def parse_args(): 
    parser = ArgumentParser(description='Rsh detector server redirecter.')
    
    def_rsh_path = "configs/rsh_conf.json"
    
    parser.add_argument('lan10_bin', type=str,
                        help='path lan10-12pci-base')
    parser.add_argument('-s', '--rsb-conf', type=str, default=def_rsh_path,
                        help='default rsb conf file pattern (default '
                             '%s)'%(def_rsh_path))
    parser.add_argument('-o', '--out-dir', type=str, default="points",
                    help='output directory (default - "points")')
    
    
    parser.add_argument('-t', '--timeout', type=int,
                        help='generate virtual events')
    parser.add_argument('--host', default='localhost',
                        help='server host (default - localhost)')
    parser.add_argument('-p', '--port', type=int, default=5555,
                        help='server port (default - 5555)')
    
    parser.add_argument('--work-port', type=int, default=5555,
                        help='programm working port (default 5555)')
    
    return parser.parse_args()
              
          
if __name__ == "__main__":
    args = parse_args()
    
    pattern = json.load(open(args.rsb_conf))
    
    if not os.path.exists(args.out_dir):
        os.makedirs(args.out_dir)
    
    loop = asyncio.get_event_loop()
    coro = loop.create_server(RshServerProtocol, "0.0.0.0", args.work_port)
    server = loop.run_until_complete(coro)
    
    print('Serving on {}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
        
    server.close()
    loop.run_until_complete(server.wait_closed())
    