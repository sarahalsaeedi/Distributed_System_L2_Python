# coding=utf-8
import argparse
import json, ast

import sys
from threading import Lock, Thread
from random import randint, random, seed
import time
import traceback
import bottle
from bottle import Bottle, request, template, run, static_file
import requests
from concurrent.futures import ThreadPoolExecutor
import itertools


# ------------------------------------------------------------------------------------------------------

class Blackboard():

    def __init__(self):
        self.content = []
        self.lock = Lock()  # use lock when you modify the content

    def get_content(self):
        with self.lock:
            cnt = self.content
        return cnt

    def set_content(self, new_content, post_type):
        with self.lock:
            if post_type == 0:
                self.content.append(new_content)
            else:
                self.content = new_content
        return


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list, election_list, rand_id):
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.id = int(ID)
        self.ip = str(IP)
        # election dictionary for (random Id -> server ip)
        self.election_dict = {}
        self.election_lock = Lock()
        self.rand_id = rand_id
        # leader dictionary for ("leader_ip" -> server ip)
        self.leader = {}
        # list containing random ids that propogate in the ring
        self.election_list = election_list
        # self.random_id = randint(0,100)
        self.servers_list = servers_list
        self.headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        # list all REST URIs
        # if you add new URIs to the server, you need to add them here
        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board', callback=self.post_index)
        self.post('/board_concurrent', callback=self.post_concurrent)
        self.post('/board_concurrent/<id:int>/modify/', callback=self.board_concurrent_modify)
        self.post('/board_concurrent/<id:int>/delete/', callback=self.board_concurrent_delete)
        self.post('/propagate', callback=self.post_propagate)
        self.post('/propagate/<id:int>/modify/', callback=self.post_propagate_modify)
        self.post('/propagate/<id:int>/delete/', callback=self.post_propagate_delete)
        self.post('/board/<id:int>/', callback=self.post_board)
        # -------------------------Leader Election Process---------------------------------
        # elect new leader
        self.post('/leader_election', callback=self.post_leader_election_thread)
        # send leader ip after election to the ring
        self.post('/coordinator', callback=self.post_coordinator)
        # -------------------------------------------------------------------
        self.get('')
        # we give access to the templates elements
        self.get('/templates/<filename:path>', callback=self.get_template)
        # You can have variables in the URI, here's an example
        # self.post('/board/<element_id:int>/', callback=self.post_board) where post_board takes an argument (integer) called element_id

    # ---------------------------------get and set election list--------------------------------------------------
    def set_election_list(self, new_list, ops):
        if ops == 1:
            self.election_list.extend(new_list)
        else:
            del self.election_list[:]

    def get_election_list(self):
        new_election_list = self.election_list
        return new_election_list

    def do_parallel_task_after_delay(self, delay, method, args=None):
        thread = Thread(target=self._wrapper_delay_and_execute,
                        args=(delay, method, args))

        thread.daemon = True
        thread.start()

    # run handshake function as thread
    def do_handshake(self, delay, method, args=None):
        thread = Thread(target=self._wrapper_delay_and_execute,
                        args=(delay, method, args))
        thread.daemon = True
        thread.start()

    # after startup, send my random id along with my ip to all other servers
    def handShake(self, server_ip, rand_id):
        self.election_dict[self.rand_id] = str(self.ip)
        params_dict = json.dumps({'server_ip': server_ip, 'randID': rand_id})
        self.propagate_to_all_servers("/propagate", params_dict, "POST")

    # send election message to my successor with my random id
    def start_election(self, server_ip, server_id, rand_id):
        success = False
        try:
            self.leader["status"] = "None"
            self.set_election_list([], 0)
            self.set_election_list([rand_id], 1)
            election_list_source = self.get_election_list()
            g = itertools.cycle(self.servers_list)
            for j in xrange(8):
                shape = next(g)
                if shape == self.ip:
                    next_server = next(g)
                    break

            for i in range(len(self.servers_list)):
                try:
                    payload = {'electionList': election_list_source}
                    res = requests.post('http://{}{}'.format(next_server, "/leader_election"),
                                        data=json.dumps(payload),
                                        headers=self.headers)
                    print("response", res)
                    if res.status_code == 200:
                        break
                except Exception as e:
                    next_server = next(g)

        except Exception as e:
            print("[ERROR] " + str(e))
        return success

    # run post_leader_election as thread
    def post_leader_election_thread(self):
        post_body_payload = request.body.read()
        thread = Thread(target=self.post_leader_election, args=(post_body_payload,))
        thread.daemon = True
        thread.start()

    # callback method for post /leader_election
    def post_leader_election(self, payload_data):
        success = False
        try:
            payload_data = json.loads(payload_data)
            election_list_datasource = payload_data['electionList']
            if self.rand_id in election_list_datasource:
                leader_ip = self.election_dict[max(election_list_datasource)]
                self.leader["leader_ip"] = leader_ip
                self.leader["status"] = "Updated"
                if self.ip == leader_ip:
                    server_status = "leader"
                else:
                    server_status = "slave"
                print("server attribute: ", self.rand_id, "server status: ", server_status)

                g = itertools.cycle(self.servers_list)
                for j in xrange(8):
                    shape = next(g)
                    if shape == self.ip:
                        next_server = next(g)
                        break

                for i in range(len(self.servers_list)):
                    try:
                        payload = {'leader_ip': leader_ip}
                        res = requests.post('http://{}{}'.format(next_server, "/coordinator"),
                                            data=json.dumps(payload),
                                            headers=self.headers)
                        print("response", res)
                        if res.status_code == 200:
                            break
                    except Exception as e:
                        next_server = next(g)


            else:
                self.set_election_list([], 0)
                self.leader["status"] = "None"
                election_list_datasource.append(self.rand_id)
                self.set_election_list(election_list_datasource, 1)
                g = itertools.cycle(self.servers_list)
                for j in xrange(8):
                    shape = next(g)
                    if shape == self.ip:
                        next_server = next(g)
                        break

                for i in range(1, len(self.servers_list)):
                    try:
                        payload = {'electionList': election_list_datasource}
                        res = requests.post('http://{}{}'.format(next_server, "/leader_election"),
                                            data=json.dumps(payload),
                                            headers=self.headers)
                        print("response", res)
                        if res.status_code == 200:
                            break
                    except Exception as e:
                        next_server = next(g)
                        print("leader is offline ")

        except Exception as e:
            print("[ERROR in Post leader election] " + str(e))
        return success

    # callback for post /coordinator
    def post_coordinator(self):
        if self.leader["status"] == "Updated":
            print("Election Finished!")
        else:
            leader = json.loads(request.body.read())
            self.leader["leader_ip"] = str(leader["leader_ip"])
            self.leader["status"] = "Updated"
            if self.ip == leader["leader_ip"]:
                server_status = "leader"
            else:
                server_status = "slave"
            print("server attribute: ", self.rand_id, "server status: ", server_status)

            g = itertools.cycle(self.servers_list)
            for j in xrange(8):
                shape = next(g)
                if shape == self.ip:
                    next_server = next(g)
                    break

            for i in range(len(self.servers_list)):
                try:
                    payload = {'leader_ip': self.leader["leader_ip"]}
                    res = requests.post('http://{}{}'.format(next_server, "/coordinator"),
                                        data=json.dumps(payload),
                                        headers=self.headers)
                    print("response", res)
                    if res.status_code == 200:
                        break
                except Exception as e:
                    next_server = next(g)

    def _wrapper_delay_and_execute(self, delay, method, args):
        time.sleep(delay)  # in sec
        method(*args)

    def contact_another_server(self, srv_ip, URI, params_dict, req='POST'):
        success = False
        try:
            if 'POST' in req:
                res = requests.post('http://{}{}'.format(srv_ip, URI), data=params_dict)

            # result can be accessed res.json()
            if res.status_code == 200:
                success = True
        except Exception as e:
            print("")
        return success

    def propagate_to_all_servers(self, URI, params_dict, req='POST'):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip:  # don't propagate to yourself
                success = self.contact_another_server(srv_ip, URI, params_dict, req)
                if not success:
                    print("[WARNING ]server {}".format(srv_ip), "is offline")

    # route to ('/')
    def index(self):
        # we must transform the blackboard as a dict for compatiobility reasons
        print('LEADER is ', self.leader)
        if self.ip == self.leader['leader_ip']:
            server_status = "Leader"
        else:
            server_status = "Slave"

        board = dict()
        board["0"] = self.blackboard.get_content()
        return template('server/templates/index.tpl',
                        board_title='Server {} ({}) Status ({}) ID ({})'.format(self.id,
                                                                                self.ip, server_status,
                                                                                str(self.rand_id)),
                        board_dict=board.iteritems(),
                        members_name_string='Alsaeedi Sarah, Ibrahim Senan')

    # get on ('/board')
    def get_board(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        content = self.blackboard.get_content()
        for i in range(len(content)):
            board["%s" % i] = content[i]
        return template('server/templates/blackboard.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=board.iteritems())

    def contact_leader(self, srv_ip, URI, itemID, update_option, params_dict, req='POST'):
        print("contact leader", srv_ip)
        success = False
        try:
            # post new entry to blackboard
            if itemID == -1:
                if 'POST' in req:
                    res = requests.post('http://{}{}'.format(srv_ip, URI),
                                        data=params_dict)
                    print(res)
                elif 'GET' in req:
                    res = requests.get('http://{}{}'.format(srv_ip, URI))
            # update item
            else:
                if 'POST' in req:
                    res = requests.post('http://{}{}/'.format(srv_ip, URI),
                                        data=params_dict)
                    print(res)
                elif 'GET' in req:
                    res = requests.get('http://{}{}/'.format(srv_ip, URI))
            # result can be accessed res.json()
            if res.status_code == 200:
                success = True
        except Exception as e:
            print("leader offline ---> start election")
            self.start_election(self.ip, self.id, self.rand_id)

        return success

    def leader_propagate_to_all_servers(self, url, URI, update_option, params_dict):
        try:
            # propogate post request to all
            if update_option == None:
                res = requests.post('http://{}{}'.format(url, URI),
                                    data=params_dict)
            # propogate post modify request to all
            else:
                res = requests.post('http://{}{}/{}/'.format(url, URI, update_option),
                                    data=params_dict)
            print("[response] " + str(res))

        except Exception as e:
            print("")

    # post on ('/')
    def post_index(self):
        try:
            new_entry = request.forms.get('entry')
            if new_entry == None:
                new_entry = request.body.read()
            if self.ip == self.leader["leader_ip"]:
                # implement the request and propogate it to all others
                self.blackboard.set_content(new_entry, 0)
                updateO = None
                params_dict = new_entry
                self.propagate_to_all_servers_executor(self.leader_propagate_to_all_servers, "/board_concurrent",
                                                       updateO,
                                                       params_dict)
            else:
                # send the request to the leader
                params_dict = new_entry
                self.contact_leader(self.leader["leader_ip"], "/board", -1, None, params_dict, req='POST')
        except Exception as e:
            print("[ERROR] " + str(e))

    # leader propagate to all server with post req
    def propagate_to_all_servers_executor(self, method, URI, update_option, params_dict):
        with ThreadPoolExecutor(max_workers=7) as executor:
            for srv_ip in self.servers_list:
                if srv_ip != self.ip:
                    future = executor.submit(self.leader_propagate_to_all_servers_thread, srv_ip, URI, update_option,
                                             params_dict)

    #
    def leader_propagate_to_all_servers_thread(self, url, URI, update_option, params_dict):
        thread = Thread(target=self.leader_propagate_to_all_servers, args=(url, URI, update_option, params_dict))
        thread.daemon = True
        thread.start()

    # post on ('/board_concurrent')
    def post_concurrent(self):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.body.read()
            print("Received: {}".format(new_entry))
            self.blackboard.set_content(new_entry, 0)
        except Exception as e:
            print("[ERROR] " + str(e))

    # post on ('/propagate')
    def post_propagate(self):
        try:
            new_entry = request.body.read()
            if new_entry.find("server_ip") == -1:
                self.blackboard.set_content(new_entry, 0)
            else:
                handshak_params = json.loads(new_entry)
                self.election_dict[handshak_params['randID']] = str(handshak_params['server_ip'])

        except Exception as e:
            print("[ERROR] " + str(e))

    def post_propagate_modify(self, id):
        try:
            new_entry = request.body.read()
            x = new_entry.split('&')
            content = self.blackboard.get_content()
            content[id] = x[0]
            self.blackboard.set_content(content, 1)
        except Exception as e:
            print("[ERROR] " + str(e))

    def post_propagate_delete(self, id):
        try:
            content = self.blackboard.get_content()
            del content[id]
            self.blackboard.set_content(content, 1)
        except Exception as e:
            print("[ERROR] " + str(e))

    # post on ('/board/element_Id')
    def post_board(self, id):
        try:
            new_entry = request.forms.get('entry')
            update_option = request.forms.get('update')
            params_dict = new_entry
            itemID = int(id)
            if new_entry == None:
                new_entry = json.loads(request.body.read())
                update_option = new_entry["update_option"]
                itemID = int(new_entry["id"])
                params_dict = new_entry["new_entry"]

            if self.ip == self.leader["leader_ip"]:
                # implement the request and propogate it to all others
                content = self.blackboard.get_content()
                content[itemID] = params_dict
                self.propagate_to_all_servers_executor(self.leader_propagate_to_all_servers,
                                                       "/board_concurrent/{}".format(itemID), update_option,
                                                       params_dict)

                if update_option == "delete":
                    del content[itemID]
                self.blackboard.set_content(content, 1)
            else:
                # send the request to the leader
                payload = {'new_entry': new_entry, 'update_option': update_option, 'id': itemID}
                self.contact_leader(self.leader["leader_ip"], "/board/{}".format(itemID), itemID, None,
                                    json.dumps(payload), req='POST')
        except Exception as e:
            print("[ERROR]" + str(e))

    # post on ('/board_concurrent/element_Id/modify')
    def board_concurrent_modify(self, id):
        try:
            new_entry = request.body.read()
            content = self.blackboard.get_content()
            content[id] = new_entry
            self.blackboard.set_content(content, 1)
        except Exception as e:
            print("[ERROR]" + str(e))

    # post on ('/board_concurrent/element_Id/delete')
    def board_concurrent_delete(self, id):
        try:
            content = self.blackboard.get_content()
            del content[id]
            self.blackboard.set_content(content, 1)
        except Exception as e:
            print("[ERROR]" + str(e))

    def get_template(self, filename):
        return static_file(filename, root='./server/templates/')

    def dynamic_network(self, server_ip):
        if server_ip == self.leader["leader_ip"]:
            sys.stderr.close()
            print("leader will go offline")
 

# ------------------------------------------------------------------------------------------------------
def main():
    PORT = 80
    parser = argparse.ArgumentParser(description='Your own implementation of the distributed blackboard')
    parser.add_argument('--id',
                        nargs='?',
                        dest='id',
                        default=1,
                        type=int,
                        help='This server ID')
    parser.add_argument('--servers',
                        nargs='?',
                        dest='srv_list',
                        default="10.1.0.1,10.1.0.2",
                        help='List of all servers present in the network')
    args = parser.parse_args()
    server_id = args.id
    server_ip = "10.1.0.{}".format(server_id)
    servers_list = args.srv_list.split(",")

    try:
        server = Server(server_id,
                        server_ip,
                        servers_list, [], randint(0, 100))
        server.leader["leader_ip"] = server.ip
        server.do_handshake(6, server.handShake, args=(server.ip, server.rand_id))
        if server.ip == servers_list[0]:
            server.do_parallel_task_after_delay(10, server.start_election, args=(server.ip, server.id, server.rand_id))
        #close leader server after 40 seconds
        server.do_parallel_task_after_delay(40, server.dynamic_network, args=(server.ip,))
        bottle.run(server,
                   host=server_ip,
                   port=PORT)

    except Exception as e:
        print("[ERROR] " + str(e))


# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
