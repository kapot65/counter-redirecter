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
import logging
import zipfile
from threading import Lock
from os import path, makedirs, remove, listdir
from argparse import ArgumentParser

from dftcp import DataforgeEnvelopeProtocol
from dftcp import DataforgeEnvelopeEchoClient as DFClient
from dfparser import serialise_to_rsh, create_message

cur_dir = path.dirname(path.realpath(__file__))
if not cur_dir in sys.path: sys.path.append(cur_dir)
del cur_dir

from utils.popen_cbk import Popen_cbk
from utils.rsb import rsb_to_df

rsh_lock = Lock()

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
    
    def cbk(self, message, client_obj, params=None):
        """
          Функция дополняет сообщения внешними метаданными
          
        """
        
        meta = message["meta"]
        data = message["data"]
        data_type = message["header"]["data_type"]
        if not self.check_junk(message["meta"]):
            
            logger.debug("-> closing transport connection")
            client_obj.transport.close()
            
            if params and type(params) is dict and "proc" in params:
                logger.debug("waiting for ext process fininshed")
                params["proc"].join()
                logger.debug("extprocess fininshed")
                
            
            if params and type(params) is dict and "filepath" in params:
                ext_meta = meta.get("external_meta", {})
                
                session = ext_meta.get("session", "no_session")
                group = ext_meta.get("group", "no_group")
                index = int(ext_meta.get("index", 0))
                hv1 = int(ext_meta.get("HV1_value", -1))
                hv2 = int(ext_meta.get("HV2_value", -1))
                
                out_dir = path.join(args.out_dir, "%s/%s"%(session, group))
                if not path.exists(out_dir):
                    makedirs(out_dir)
                    
                out_dir = path.join(out_dir, "set_%s"%(len(listdir(out_dir))))
                if not path.exists(out_dir):
                    makedirs(out_dir)
                
                out_file = "p%s"%(index)
                if hv1 != -1 or hv2 != -1:
                    out_file += "("
                    if hv1 != -1:
                        out_file += "HV1=%s"%(hv1)
                        if hv2 != -1:
                            out_file += ";"
                    if hv2 != -1:
                        out_file += "HV2=%s"%(hv2)
                    out_file += ")"
                
                
                meta_df, data_df = rsb_to_df(ext_meta, params["filepath"],
                                             threshold=args.zero_thresh,
                                             area_l=args.zero_area_l,
                                             area_r=args.zero_area_r)
                
                with open(path.join(out_dir, out_file), "wb") as file:
                    file.write(create_message(meta_df, data_df))
                
                if not args.testfile:
                    remove(params["filepath"])
            
        self.send_message(meta, data, data_type)
        
    def forward_message(self, meta, data, params):
        """
          Проброс сообщения на сервер КАМАК
          
          @meta - метаданные сообщения
          @data - бинарные данные сообщения
          @params - параметры, передаваемые в callback (self.cbk)
          
        """
        loop = asyncio.new_event_loop()
        
        callback = lambda msg, client: self.cbk(msg, client, params)
        client = lambda: DFClient(loop, meta, callback=callback, 
                                  timeout_sec=args.timeout)
        
        coro = loop.create_connection(client, args.host, args.port)
        
        loop.run_until_complete(coro)
        loop.run_forever()
        
    def process_message(self, message):
        """
          Обработка входящих сообщений.
          В этой функции происходит анализ входящей команды. Если приходит
          команда на сбор точки - сервер вызывает программу для набора точки
          с платы lan10-12pci. В остальных случаях сервер просто транслирует 
          команду на основной сервер.
          
        """
        meta = message['meta']
        params = None
        
        if 'command_type' in  meta:
            logger.debug("-> %s"%(meta['command_type']))
        else:
            logger.warning("-> unrecognized message^ %s"%(meta))
  
        if 'command_type' in meta and meta['command_type'] == "acquire_point":
            cur_patt = pattern
            cur_patt["aquisition_time"] = int(meta["acquisition_time"])*1000
            
            fname = "%s.rsb"%(time.strftime("%Y%m%d-%H%M%S"))
            fname_abs = path.abspath(path.join(args.out_dir, fname))
            
            if args.testfile:
                rsh_acq_command = ["python", '-c', 
                                   'import time; time.sleep(%s)'%
                                   (meta["acquisition_time"])]
                fname_abs = path.abspath(args.testfile)
            else:
                with open(fname_abs, "w") as file:
                    file.write(serialise_to_rsh(cur_patt))
                rsh_acq_command = [args.lan10_bin, fname_abs, "-s"]
                
            
            logger.debug("lan10 acquisition process started (file - %s)"
                         %(fname_abs))
            
            if rsh_lock.locked():
                logger.debug("board acquisition locked; waiting...")
                
            rsh_lock.acquire()
            end_cbk = lambda: logger.debug("acquisition %s done"%(fname_abs));\
                      rsh_lock.release()
            
            params = {"proc": Popen_cbk(end_cbk, rsh_acq_command),
                      "filepath": fname_abs}
            
        
        self.forward_message(meta, message['data'], params)
        

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
    
    test_grp = parser.add_argument_group("Test")
    test_grp.add_argument('--test', action="store_true",
                        help='use default rsb file instead of acquisition')
    
    def_rsb = path.abspath(path.join(path.dirname(__file__), 
                                     "tests/data/test_point.zip"))
    test_grp.add_argument('--testfile', type=str, default=def_rsb,
                        help='default rsb filepath (default - %s)'%(def_rsb))
    
    return parser.parse_args()
              
          
if __name__ == "__main__":
    args = parse_args()
    
    if not "logger" in globals(): 
        logger = init_logger()
        
    if args.test and args.testfile.endswith(".zip"):
        with zipfile.ZipFile(args.testfile,"r") as zip_ref:
            zip_ref.extractall(path.dirname(args.testfile))
            args.testfile = args.testfile[:-4] + '.rsb'
    
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
    