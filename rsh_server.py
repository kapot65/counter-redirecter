#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 13 15:21:37 2017

@author: chernov
"""

import sys
import json
import time
import asyncio
import subprocess
import logging
from os import path, makedirs
from argparse import ArgumentParser

from dftcp import DataforgeEnvelopeProtocol
from dftcp import DataforgeEnvelopeEchoClient as DFClient

cur_dir = path.dirname(path.realpath(__file__))
if not cur_dir in sys.path: sys.path.append(cur_dir)
del cur_dir

from utils.popen_cbk import Popen_cbk
from utils.rsb_serializer import serialise_to_rsb
from utils.rsb import zero_suppression

class RshServerProtocol(DataforgeEnvelopeProtocol):
    """
      Сервер транслирует и сниффит все сообщения.
      Если через серевер проходит сообщение с командой на набор - сервер 
      запускает плату Лан10-12PCI на набор на то же время и вставляет 
      информацию о набранном файле в ответное сообщение.
      
    """
    def check_junk(self, meta):
        """
         Функция проверяет, является ли пересылаемое сообщение информационным
         или конечным ответом
         
        """
        if "reply_type" in meta and meta["reply_type"] == "acquisition_status":
            logger.debug("<- %s - junk"%(meta["reply_type"]))
            return True
        elif meta == {}:
            logger.debug("<- empty message - junk")
            return True
        else:
            return False
    
    def cbk(self, message, client_obj, ext_meta, ext_proc=None):
        meta = message["meta"]
        
        if "external_meta" in meta:
            meta["external_meta"] = {**meta["external_meta"], **ext_meta}
        else:
            meta["external_meta"] = ext_meta
            
        if not self.check_junk(message["meta"]):
            
            logger.debug("-> closing transport connection")
            client_obj.transport.close()
            
            if ext_proc:
                logger.debug("waiting for ext process fininshed")
                ext_proc.join()
                logger.debug("for extprocess fininshed")
                
                if "rsb" in ext_meta:
                    fname = ext_meta["rsb"]["filepath"]
                    
                    if args.zero_suppr:
                        logger.debug("applying zero-suppr: file - %s"%(fname))
                        zero_suppression(fname, args.zero_thresh, 
                                         args.zero_area_l, 
                                         args.zero_area_r)
                        logger.debug("zero-suppr applied: file - %s"%(fname))
                        
                        zsuppr_meta = {"threshold": args.zero_thresh,
                                       "area_left": args.zero_area_l,
                                       "area_right": args.zero_area_r}
                        
                        meta["external_meta"]["rsb"]\
                            ["zero_suppression"] = zsuppr_meta
                    
                    logger.debug("zipping %s started"%(fname))       
                    Popen_cbk(lambda: logger.debug("zipping %s done"%(fname)),
                              ["zip", "-1", "-j" ,"%s.zip"%(fname), 
                              "-rm", fname])
            
        self.send_message(meta, message["data"], 
                          message["header"]["data_type"])
        
        
    def forward_message(self, meta, data, ext_meta={}, ext_proc=None):
        loop = asyncio.new_event_loop()
        
        callback = lambda msg, client: self.cbk(msg, client, 
                                                ext_meta, ext_proc)
        client = lambda: DFClient(loop, meta, callback=callback, 
                                  timeout_sec=args.timeout)
        
        coro = loop.create_connection(client, args.host, args.port)
        
        loop.run_until_complete(coro)
        loop.run_forever()
        
    def process_message(self, message):
        
        meta = message['meta']
        ext_meta = {}
        ext_proc = None
        
        if 'command_type' in  meta:
            logger.debug("-> %s"%(meta['command_type']))
        else:
            logger.warning("-> unrecognized message^ %s"%(meta))
  
        if 'command_type' in meta and meta['command_type'] == "acquire_point":
            cur_patt = pattern
            cur_patt["aquisition_time"] = int(meta["acquisition_time"])*1000
            
            fname = "%s.rsb"%(time.strftime("%Y%m%d-%H%M%S"))
            fname_abs = path.abspath(path.join(args.out_dir, fname))
            
            with open(fname_abs, "w") as file:
                file.write(serialise_to_rsb(cur_patt))
                
            
            logger.debug("lan10 acquisition process started "
                         "(file - %s)"%(fname_abs))
            end_cbk = lambda: logger.debug("acquisition %s done"%(fname_abs))
            ext_proc = Popen_cbk(end_cbk, [args.lan10_bin, fname_abs, "-s"])
            
            ext_meta["rsb"] = {"filepath": fname_abs}
            
        
        self.forward_message(meta, message['data'], ext_meta, ext_proc)
        

def init_logger():
    logger = logging.getLogger('rsh_server')
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(args.logfile)
    if args.verbose:
        fh.setLevel(logging.DEBUG)
    else:
        fh.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    if args.verbose:
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.WARNING)

    fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(fmt)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger
    
                        
def parse_args(): 
    parser = ArgumentParser(description='Rsh detector server redirecter.')

    
    in_grp = parser.add_argument_group("Input")
    in_grp.add_argument('lan10_bin', type=str,
                        help='path lan10-12pci-base')
    in_grp.add_argument('-t', '--timeout', type=int, default=300,
                        help='command execution timeout in seconds '
                        '(default - 300)')
    in_grp.add_argument('--host', default='localhost',
                        help='server host (default - localhost)')
    in_grp.add_argument('-p', '--port', type=int, default=5555,
                        help='server port (default - 5555)')
    
    out_grp = parser.add_argument_group("Output")
    out_grp.add_argument('-o', '--out-dir', type=str, default="points",
                    help='output directory (default - "points")')
    out_grp.add_argument('--work-port', type=int, default=5555,
                        help='programm working port (default 5555)')
    
    acq_grp = parser.add_argument_group("Acquisition")
    def_rsh_path = "configs/rsh_conf.json"
    acq_grp.add_argument('-s', '--rsb-conf', type=str, default=def_rsh_path,
                        help='default rsb conf file pattern (default '
                             '%s)'%(def_rsh_path))
    acq_grp.add_argument('-z', '--zero-suppr', action="store_true",
                        help='use zero suppression on acquired data')
    acq_grp.add_argument('--zero-thresh', type=int, default=700,
                        help='zero suppression threshold in bins '
                        '(default - 500)')
    acq_grp.add_argument('--zero-area-l', type=int, default=50,
                        help='left neighborhood area size (in bins) which will'
                        ' be  saved during zero suppression'
                        '(default - 50)')
    acq_grp.add_argument('--zero-area-r', type=int, default=100,
                        help='left neighborhood area size (in bins) which will'
                        ' be  saved during zero suppression'
                        '(default - 100)')
    
    parser.add_argument('-l', '--logfile', default="rsh_server.log",
                        help='log filepath')
    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                    action="store_true")
    
    return parser.parse_args()
              
          
if __name__ == "__main__":
    args = parse_args()
    
    if not "logger" in globals(): 
        logger = init_logger()
    
    
    pattern = json.load(open(args.rsb_conf))
    
    if not path.exists(args.out_dir):
        makedirs(args.out_dir)
    
    loop = asyncio.get_event_loop()
    coro = loop.create_server(RshServerProtocol, "0.0.0.0", args.work_port)
    server = loop.run_until_complete(coro)
 
    print('Serving on {}'.format(server.sockets[0].getsockname()))
    logger.info('Serving on {}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Programm stoped by user input")
        pass
        
    server.close()
    loop.run_until_complete(server.wait_closed())
    