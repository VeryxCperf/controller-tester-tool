import requests
import json
import argparse
import sys
import netaddr
import threading
import Queue
import random
import copy
import time
import itertools
import subprocess
import shlex
from itertools import dropwhile
from subprocess import check_output as qx
import time,threading,os
import logging

##Configure the filenames in below the main function also
filename1 = "output_http.txt"
filename2 = "output_flow.txt"


print "\nThis script calculate the \"Proactive Path Provisioning Time\" with bulk flows install from Northbound insterface in single REST request.\n"

print "\nNote:"
print "      Make sure the SDN controller and mininet is running before start the test."
print "      Use --fpr option to send bulk flows in single REST request."
print "      Option --NBport and --SBport is mandatory to run the script otherwise"
print "      script use the default(eth0) interface.\n\n"

flow_template = {
	"id": "2",
	"match": {
             "ethernet-match": {
                 "ethernet-type": {
                     "type": 2048
                 }
             },
             "ipv4-destination": "10.0.20.0/24"
         },
         "priority": 2,
         "table_id": 0
     }
odl_node_url = '/restconf/config/opendaylight-inventory:nodes/node/'


print "Step 1: Initiating packet caputre at the NB and SB controller interface.\n"

##Starting the packer capture from northbound and southbound interface.
##Here the tshark capture the "HTTP POST" request message from northbound interface and "FLOW_MOD" message from southbound interface.

def work1():
    http_post = subprocess.check_output(shlex.split("""tshark -i "%s" -Y "http.request.method == POST" -t a -a duration:60""" %port1))
    target = open(filename1, 'w')
    target.write(http_post)

def work2():
    global inargs
    flow_mod = subprocess.check_output(shlex.split("""tshark -i "%s" -V -Y "openflow_v4.type == OFPT_FLOW_MOD && openflow_v4.flowmod.command == OFPFC_ADD" -t a -a duration:60""" %port2))
    target = open(filename2, 'w')
    target.write(flow_mod)
    flow_mod1=subprocess.check_output(shlex.split("""grep -R "Arrival Time" output_flow.txt"""))
    target = open('output_flow_mod.txt', 'w')
    target.write(flow_mod1)
    flow_mod2=subprocess.check_output(shlex.split("""grep -R "OFPFC_ADD" output_flow.txt"""))
    target = open('output_flow_mod_count.txt', 'w')
    target.write(flow_mod2)

def work3():
    flow_mod = subprocess.check_output(shlex.split("""tshark -i "%s" -Y "openflow_v4.type == OFPT_FLOW_MOD && openflow_v4.flowmod.command == OFPFC_ADD" -t a -a duration:60""" %port2))
    target = open(filename2, 'w')
    target.write(flow_mod)

		
class Timer(object):
         def __init__(self, verbose=False):
             self.verbose = verbose
    
         def __enter__(self):
             self.start = time.time()
             return self
     
         def __exit__(self, *args):
             self.end = time.time()
             self.secs = self.end - self.start
             self.msecs = self.secs * 1000  # millisecs
             if self.verbose:
                 print("elapsed time: %f ms" % self.msecs)
     
   
class Counter(object):
         def __init__(self, start=0):
             self.lock = threading.Lock()
             self.value = start
     
         def increment(self, value=1):
             self.lock.acquire()
             val = self.value
             try:
                 self.value += value
             finally:
                 self.lock.release()
             return val
     
   
def _prepare_post(cntl, method, flows, template=None):
         """Creates a POST http requests to configure a flow in configuration datastore.
     
         Args:
             :param cntl: controller's ip address or hostname
     
             :param method: determines http request method
     
             :param flows: list of flow details
     
             :param template: flow template to be to be filled
     
         Returns:
             :returns req: http request object
         """
         flow_list = []
	  
         for dev_id, ip in (flows):
             flow = copy.deepcopy(template)
             flow["id"] = ip
             flow["match"]["ipv4-destination"] = '%s/32' % str(netaddr.IPAddress(ip))
             flow_list.append(flow)
         body = {"flow": flow_list}
         url = 'http://' + cntl + ':8181' + odl_node_url + dev_id + '/table/0'
         req_data = json.dumps(body)
         req = requests.Request(method, url, headers={'Content-Type': 'application/json'},
                                data=req_data, auth=('admin', 'admin'))
         return req
     
   
def _prepare_delete(cntl, method, flows, template=None):
         """Creates a DELETE http requests to configure a flow in configuration datastore.
     
         Args:
             :param cntl: controller's ip address or hostname
     
             :param method: determines http request method
     
             :param flows: list of flow details
     
             :param template: flow template to be to be filled
     
         Returns:
             :returns req: http request object
         """
         dev_id, flow_id = flows[0]
         url = 'http://' + cntl + ':8181' + odl_node_url + dev_id + '/table/0/flow/' + str(flow_id)
         req = requests.Request(method, url, headers={'Content-Type': 'application/json'},
                                data=None, auth=('admin', 'admin'))
         return req
  
def _wt_request_sender(thread_id, preparefnc, inqueue=None, exitevent=None, controllers=[], restport='',
                            template=None, outqueue=None, method=None):
         """The funcion sends http requests.
   
        Runs in the working thread. It reads out flow details from the queue and sends apropriate http requests
         to the controller
  
         Args:
             :param thread_id: thread id
   
             :param preparefnc: function to preparesthe http request
  
             :param inqueue: input queue, flow details are comming from here
     
             :param exitevent: event to notify working thread that parent (task executor) stopped filling the input queue
  
             :param controllers: a list of controllers' ip addresses or hostnames
  
             :param restport: restconf port
  
             :param template: flow template used for creating flow content
     
             :param outqueue: queue where the results should be put
  
             :param method: method derermines the type of http request
  
         Returns:
             nothing, results must be put into the output queue
         """
         ses = requests.Session()
         cntl = controllers[0]
         counter = [0 for i in range(600)]
         loop = True
  
         while loop:
             try:
                 flowlist = inqueue.get(timeout=1)
             except Queue.Empty:
                 if exitevent.is_set() and inqueue.empty():
                     loop = False
                 continue
             req = preparefnc(cntl, method, flowlist, template=template)
             # prep = ses.prepare_request(req)
             prep = req.prepare()
             try:
                 rsp = ses.send(prep, timeout=5)
             except requests.exceptions.Timeout:
                 counter[99] += 1
                 continue
             counter[rsp.status_code] += 1
         res = {}
         for i, v in enumerate(counter):
             if v > 0:
                 res[i] = v
         outqueue.put(res)
  

def get_device_ids(controller, port):
         """Returns a list of switch ids"""
          
         ids = []
	 rsp = requests.get(url='http://{0}:{1}/restconf/operational/opendaylight-inventory:nodes'
                         .format(controller, port), auth=('admin', 'admin'))
         if rsp.status_code != 200:
             return []
         try:
             devices = json.loads(rsp.content)['nodes']['node']
             ids = [d['id'] for d in devices]
         except KeyError:
            pass
         return ids
  
  
def get_flow_ids(controller, port):
         """Returns a list of flow ids"""
         ids = []
         device_ids = get_device_ids(controller, port)
         for device_id in device_ids:
             rsp = requests.get(url='http://{0}:{1}/restconf/operational/opendaylight-inventory:nodes/node/%s/table/0'
                                .format(controller, port) % device_id, auth=('admin', 'admin'))
             if rsp.status_code != 200:
                 return []
             try:
                 flows = json.loads(rsp.content)['flow-node-inventory:table'][0]['flow']
                 for f in flows:
                     ids.append(f['id'])
             except KeyError:
                 pass
         return ids
  
 
def main(*argv):
  	  
         parser = argparse.ArgumentParser(description='Flow programming performance test: First adds and then deletes flows '
                                                      'into the config tree, as specified by optional parameters.')
  
         parser.add_argument('--host', default='127.0.0.1',
                             help='Host where ones controller is running (default is 127.0.0.1)')
         parser.add_argument('--port', default='8181',
                             help='Port on which onos\'s RESTCONF is listening (default is 8181)')
         parser.add_argument('--threads', type=int, default=1,
                             help='Number of request worker threads to start in each cycle; default=1. '
                                  'Each thread will add/delete <FLOWS> flows.')
         parser.add_argument('--flows', type=int, default=10,
                             help='Number of flows that will be added/deleted in total, default 10')
         parser.add_argument('--fpr', type=int, default=1,
                             help='Number of flows per REST request, default 1')
         parser.add_argument('--NBport', type=str,default="eth0", 
                             help='Northbound interface(REST interface) connected with Controller, default eth0')
         parser.add_argument('--SBport', type=str,default="eth0",
                             help='Southbound interface(Openflow interface) connected with Controller, default eth0')
         parser.add_argument('--timeout', type=int, default=100,
                             help='The maximum time (seconds) to wait between the add and delete cycles; default=100')
         parser.add_argument('--no-delete', dest='no_delete', action='store_true', default=False,
                             help='Delete all added flows one by one, benchmark delete '
                                  'performance.')
         parser.add_argument('--bulk-delete', dest='bulk_delete', action='store_true', default=False,
                             help='Delete all flows in bulk; default=False')
         parser.add_argument('--bulkAdd',type=str, default=False,
                             help='Install all flows in bulk with single REST; default=False')
         parser.add_argument('--outfile', default='', help='Stores add and delete flow rest api rate; default=""')
  
         in_args = parser.parse_args(*argv)
         global port1
         global port2
         global No_of_flows
         global bulk
         No_of_flows = in_args.flows
	 port1 = in_args.NBport
         port2 =  in_args.SBport
         bulk = in_args.bulkAdd
         print in_args

##Thread start the both tshark capture paralally to capture the "HTTP POST" & "FLOW_MOD".

	 threads = []
	 t1 = threading.Thread(target=work1)
	 t2 = threading.Thread(target=work2)
	 t3 = threading.Thread(target=work3)
         threads.append(t1)
	 threads.append(t2)
         threads.append(t3)
         t1.start()
         
         if bulk=='True':
            t2.start()
            time.sleep(5)
	 else:
            t3.start()
            time.sleep(5)
         
         # get device ids
         base_dev_ids = get_device_ids(controller=in_args.host, port=in_args.port)
         base_flow_ids = get_flow_ids(controller=in_args.host, port=in_args.port)
         # ip
         ip_addr = Counter(int(netaddr.IPAddress('10.0.0.1')))
         # prepare func
         preparefnc = _prepare_post
   
         base_num_flows = len(base_flow_ids)
         print "\nStep 2: Collecting the default flows count in OVS\n"
         print "        BASELINE:"
         print "            devices:", len(base_dev_ids)
         print "            flows  :", base_num_flows
         
         # lets fill the queue for workers
         nflows = 0
         flow_list = []
         flow_details = []
         sendqueue = Queue.Queue()
         dev_id = random.choice(base_dev_ids)
         print "\nStep 3: Provisioning",in_args.flows,"Flows to",dev_id,"switch from NB\n"
         flow_range=in_args.flows
         for i in range(in_args.flows):
             dst_ip = ip_addr.increment()
             flow_list.append((dev_id, dst_ip))
             flow_details.append((dev_id, dst_ip))
             nflows += 1
             if nflows == in_args.fpr:
                 sendqueue.put(flow_list)
                 nflows = 0
                 flow_list = []
                 dev_id = random.choice(base_dev_ids)
  
         # result_gueue
         resultqueue = Queue.Queue()
         # creaet exit event
         exitevent = threading.Event()
  
         # run workers
         with Timer() as tmr:
             threads = []
             for i in range(int(in_args.threads)):
                 thr = threading.Thread(target=_wt_request_sender, args=(i, preparefnc),
                                        kwargs={"inqueue": sendqueue, "exitevent": exitevent,
                                                "controllers": [in_args.host], "restport": in_args.port,
                                                "template": flow_template, "outqueue": resultqueue, "method": "POST"})
                 threads.append(thr)
                 thr.start()
 
             exitevent.set()
    
             result = {}
             # waitng for reqults and sum them up
             for t in threads:
                 t.join()
                 # reading partial resutls from sender thread
                 part_result = resultqueue.get()
                 for k, v in part_result.iteritems():
                     if k not in result:
                        result[k] = v
                     else:
                         result[k] += v
   
         print "\n        Added", in_args.flows, "flows in", tmr.secs, "seconds", result,"\n"
         add_details = {"duration": tmr.secs, "flows": len(flow_details)}
 
	 print "\nStep 4: Wait for all the flows to be installed in OVS or the expiry of test duration (60 Seconds)\n" 

         # lets print some stats
	 print "        Stats monitoring ..."
         rounds = 200
         with Timer() as t:
             for i in range(rounds):
                 reported_flows = len(get_flow_ids(controller=in_args.host, port=in_args.port))
                 expected_flows = base_num_flows + in_args.flows
                 print "        Reported Flows: %d/%d" % (reported_flows, expected_flows)
                 if reported_flows >= expected_flows:
                     break
                 time.sleep(5)
  
         if i < rounds:
             print "        ... monitoring finished in +%d seconds\n\n" % t.secs
         else:
             print "        ... monitoring aborted after %d rounds, elapsed time %d\n\n" % (rounds, t.secs)
  
         if in_args.no_delete:
             return

	 print "Step 5: Remove the installed flows in OVS after the expire of given timeout.\n"
         # sleep in between
         time.sleep(in_args.timeout)
	  
 
         print "      Flows to be removed: %d" % len(flow_details)
         # lets fill the queue for workers
         sendqueue = Queue.Queue()
         for fld in flow_details:
             sendqueue.put([fld])
    
         # result_gueue
         resultqueue = Queue.Queue()
         # creaet exit event
         exitevent = threading.Event()
  
        # run workers
         preparefnc = _prepare_delete
         with Timer() as tmr:
             if in_args.bulk_delete:
                 url = 'http://' + in_args.host + ':' + in_args.port
                 url += '/restconf/config/opendaylight-inventory:nodes'
                 rsp = requests.delete(url, headers={'Content-Type': 'application/json'}, auth=('admin', 'admin'))
                 result = {rsp.status_code: 1}
             else:
                 threads = []
                 for i in range(int(in_args.threads)):
                     thr = threading.Thread(target=_wt_request_sender, args=(i, preparefnc),
                                            kwargs={"inqueue": sendqueue, "exitevent": exitevent,
                                                    "controllers": [in_args.host], "restport": in_args.port,
                                                    "template": None, "outqueue": resultqueue, "method": "DELETE"})
                     threads.append(thr)
                     thr.start()
     
                 exitevent.set()
     
                 result = {}
                 # waitng for results and sum them up
                 for t in threads:
                     t.join()
                     # reading partial resutls from sender thread
                     part_result = resultqueue.get()
                     for k, v in part_result.iteritems():
                         if k not in result:
                             result[k] = v
                         else:
                             result[k] += v
    
         print "      Removed", len(flow_details), "flows in", tmr.secs, "seconds", result
         del_details = {"duration": tmr.secs, "flows": len(flow_details)}
  
         print "\n        Stats monitoring ..."
         rounds = 200
         with Timer() as t:
             for i in range(rounds):
                 reported_flows = len(get_flow_ids(controller=in_args.host, port=in_args.port))
                 expected_flows = base_num_flows
                 print "        Reported Flows: %d/%d" % (reported_flows, expected_flows)
                 if reported_flows <= expected_flows:
                     break
                 time.sleep(5)
  
         if i < rounds:
             print "        ... monitoring finished in +%d seconds\n\n" % t.secs
         else:
             print "        ... monitoring aborted after %d rounds, elapsed time %d\n\n" % (rounds, t.secs)
  
         if in_args.outfile != "":
             addrate = add_details['flows'] / add_details['duration']
             delrate = del_details['flows'] / del_details['duration']
             print "addrate", addrate
             print "delrate", delrate
  
             with open(in_args.outfile, "wt") as fd:
                 fd.write("AddRate,DeleteRate\n")
                 fd.write("{0},{1}\n".format(addrate, delrate))

      
if __name__ == "__main__":
         main(sys.argv[1:])

print "Step 6: Stop Packet Capture in NB & SB interfaces\n"	     
print "        Waiting for packet capture to close the process....\n"
time.sleep(60)

filename1 = "output_http.txt"
filename2 = "output_flow.txt"

##Here the time different(T1F1 - T1H1) is calculated between FLOW_MOD time stamp and HTTP POST time stamp.
print "Step 7: Calculate the Proactive Flow Provisioning Time\n"

if bulk=='True':
    Time=0
    Time1=0
    AvgTime=0
    for i in range (0,int(No_of_flows)):
           j = i+1
           with open('output_flow_mod.txt') as f:
                for line in itertools.islice(f, i, j):
                  a=line.index('.')
                  b=a-2
                  c=a+7
                  T1F1=line[b:c]

           with open(filename1) as f:
                line2=[i for i in f.read().split('\n') if i][-1]
                a=line2.index('.')
                b=a-2
                c=a+7
                T1H1=line2[b:c]
                T1F1=float(T1F1)
                T1H1=float(T1H1)
                Time = T1F1 - T1H1
                Time1 = Time*1000


##Here the number captured flow install message and flow_mod message is calculated.
    with open(filename1) as myfile:
        count = sum(1 for line in myfile)
        print "        Numer of flow install message send to controller:",count,"\n"
    with open('output_flow_mod_count.txt') as myfile:
        count1 = sum(1 for line in myfile)
        print "        Number of flow_mod message received from controller:",count1,"\n"


    print "        Proactive Flow Provisioning Time:",Time1,"milliseconds"
    print "\n"

##Delete the captured files.
    os.remove(filename1)
    os.remove(filename2)
    os.remove('output_flow_mod.txt')
    os.remove('output_flow_mod_count.txt')

else:
    Time=0
    AvgTime=0
    vol=[]
    count = 0
    count1 = 0
    minimum = 0
    maximum = 0	
		     
    for i in range (0,int(No_of_flows)):
            j = i+1
            with open(filename2) as f:
                    for line in itertools.islice(f, i, j): 
                      a=line.index('.')
                      b=a-2
                      c=a+7
                      T1F1=line[b:c]
                      with open(filename1) as f:
                              for line2 in itertools.islice(f, i, j): 
                               a=line2.index('.')
                               b=a-2
                               c=a+7
                               T1H1=line2[b:c]
                               T1F1=float(T1F1)
                               T1H1=float(T1H1)
                               Time = T1F1 - T1H1
                               Time1 = Time*1000
			       vol.append(Time1)	
			       AvgTime=AvgTime+Time1
	      
##Here the number captured flow install message and flow_mod message is calculated.  
    with open(filename1) as myfile:
        count = sum(1 for line in myfile)
        print "        Numer of flow install message send to controller:",count,"\n"
    with open(filename2) as myfile:
        count1 = sum(1 for line in myfile)
        print "        Number of flow_mod message received from controller:",count1,"\n"

##Checking the minimum and maximum provisioning time
	AvgTime=AvgTime/count
	minimum =min(vol)
	maximum =max(vol)

    print "        Proactive Flow Provisioning Time:","min / max / avg:",minimum,"/",maximum,"/",AvgTime,"milliseconds"
    print "\n"
##Delete the captured files.
    os.remove(filename1)
    os.remove(filename2)
