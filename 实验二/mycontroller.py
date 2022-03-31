#!/usr/bin/env python3
import argparse
import os
import sys
from time import sleep

import grpc

# Import P4Runtime lib from parent utils dir
# Probably there's a better way of doing this.
sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '../../utils/'))
import p4runtime_lib.bmv2
import p4runtime_lib.helper
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections
# 为交换机指定端口号
SWITCH_TO_HOST_PORT = 1
SWITCH_TO_SWITCH_PORT = 2


def writeTunnelRules(p4info_helper, ingress_sw, egress_sw, tunnel_id,
                     dst_eth_addr, dst_ip_addr):
    """
    Installs three rules:
    1) An tunnel ingress rule on the ingress switch in the ipv4_lpm table that
       encapsulates traffic into a tunnel with the specified ID
       入路由中的ipv4_lpm表的入隧道规则，将流量封装进指定ID的隧道中
    2) A transit rule on the ingress switch that forwards traffic based on
       the specified ID
       **（TODO）**入路由中的运输规则，基于指定的隧道ID转发流量
    3) An tunnel egress rule on the egress switch that decapsulates traffic
       with the specified ID and sends it to the host
       在出路由中的规则，使用特定的ID对流量解封装，并且发送流量到主机
    :param p4info_helper: the P4Info helper
    :param ingress_sw: the ingress switch connection
    :param egress_sw: the egress switch connection
    :param tunnel_id: the specified tunnel ID
    :param dst_eth_addr: the destination IP to match in the ingress rule
    :param dst_ip_addr: the destination Ethernet address to write in the
                        egress rule
    """
    # 1) Tunnel Ingress Rule
    # 使用p4info_helper这个解析器来将规则转化为P4Runtime能够识别的形式。
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm", # 设置匹配成功对应的动作名，该动作参数为传入的tunnel_id
        match_fields={
            "hdr.ipv4.dstAddr": (dst_ip_addr, 32) 
        },
        action_name="MyIngress.myTunnel_ingress", # 设置匹配成功对应的动作名
        action_params={  
            "dst_id": tunnel_id,
        })
    ingress_sw.WriteTableEntry(table_entry) # 调用WriteTableEntry()，将生成的匹配动作表项加入交换机
    print("Installed ingress tunnel rule on %s" % ingress_sw.name)

    # 2) Tunnel Transit Rule
    # The rule will need to be added to the myTunnel_exact table and match on
    # the tunnel ID (hdr.myTunnel.dst_id). Traffic will need to be forwarded
    # using the myTunnel_forward action on the port connected to the next switch.
    #
    # For our simple topology, switch 1 and switch 2 are connected using a
    # link attached to port 2 on both switches. We have defined a variable at
    # the top of the file, SWITCH_TO_SWITCH_PORT, that you can use as the output
    # port for this action.
    #
    # We will only need a transit rule on the ingress switch because we are
    # using a simple topology. In general, you'll need on transit rule for
    # each switch in the path (except the last switch, which has the egress rule),
    # and you will need to select the port dynamically for each switch based on
    # your topology.

    # TODO build the transit rule
    # TODO install the transit rule on the ingress switch
    print("TODO Install transit tunnel rule")

    # 3) Tunnel Egress Rule
    # For our simple topology, the host will always be located on the
    # SWITCH_TO_HOST_PORT (port 1).
    # In general, you will need to keep track of which port the host is
    # connected to.
    table_entry = p4info_helper.buildTableEntry( 
        table_name="MyIngress.myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnel_id
        },
        action_name="MyIngress.myTunnel_egress",
        action_params={
            "dstAddr": dst_eth_addr,
            "port": SWITCH_TO_HOST_PORT
        })
    egress_sw.WriteTableEntry(table_entry)
    print("Installed egress tunnel rule on %s" % egress_sw.name)


def readTableRules(p4info_helper, sw):
    """
    Reads the table entries from all tables on the switch.
    :param p4info_helper: the P4Info helper
    :param sw: the switch connection
    """
    print('\n----- Reading tables rules for %s -----' % sw.name)
    for response in sw.ReadTableEntries():
        for entity in response.entities:
            entry = entity.table_entry
            # TODO For extra credit, you can use the p4info_helper to translate
            #      the IDs in the entry to names
            # 获取entry.table_id
            table_name = p4info_helper.get_tables_name(entry.table_id) 
            print('%s: ' % table_name, end=' ')	# 打印出表名
            for m in entry.match: # 对每一个匹配项进行打印
                print(p4info_helper.get_match_field_name(table_name, m.field_id), end=' ')
                print('%r' % (p4info_helper.get_match_field_value(m),), end=' ')
            action = entry.action.action #获取入口动作
            action_name = p4info_helper.get_actions_name(action.action_id) 
            print('->', action_name, end=' ') #打印入口动作
            for j in action.params: 
                print(p4info_helper.get_action_param_name(action_name, j.param_id), end=' ') #打印参数名
                print('%r' % j.value, end=' ')
            print(entry)
            print('-----')

# 从交换机中读具体的索引对应的计数器
# counter能够计数数据包个数，数据总比特位数。
def printCounter(p4info_helper, sw, counter_name, index):
    """
    Reads the specified counter at the specified index from the switch. In our
    program, the index is the tunnel ID. If the index is 0, it will return all
    values from the counter.
    :param p4info_helper: the P4Info helper
    :param sw:  the switch connection
    :param counter_name: the name of the counter from the P4 program
    :param index: the counter index (in our case, the tunnel ID)
    """
    for response in sw.ReadCounters(p4info_helper.get_counters_id(counter_name), index):
        for entity in response.entities:
            counter = entity.counter_entry
            print("%s %s %d: %d packets (%d bytes)" % (
                sw.name, counter_name, index,
                counter.data.packet_count, counter.data.byte_count
            ))

def main(p4info_file_path, bmv2_file_path):
    # Instantiate a P4Runtime helper from the p4info file
    # 对p4info_helper对象进行初始化
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    try:
        # Create a switch connection object for s1 and s2;
        # this is backed by a P4Runtime gRPC connection.
        # Also, dump all P4Runtime messages sent to switch to given txt files.
        s1 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s1',
            address='127.0.0.1:50051',
            device_id=0,
            proto_dump_file='logs/s1-p4runtime-requests.txt')
        s2 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='s2',
            address='127.0.0.1:50052',
            device_id=1,
            proto_dump_file='logs/s2-p4runtime-requests.txt')

        # Send master arbitration update message to establish this controller as
        # master (required by P4Runtime before performing any other write operation)
        s1.MasterArbitrationUpdate()
        s2.MasterArbitrationUpdate()

        # Install the P4 program on the switches
        s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s1")
        s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on s2")

        # Write the rules that tunnel traffic from h1 to h2
        writeTunnelRules(p4info_helper, ingress_sw=s1, egress_sw=s2, tunnel_id=100,
                         dst_eth_addr="08:00:00:00:02:22", dst_ip_addr="10.0.2.2")

        # Write the rules that tunnel traffic from h2 to h1
        writeTunnelRules(p4info_helper, ingress_sw=s2, egress_sw=s1, tunnel_id=200,
                         dst_eth_addr="08:00:00:00:01:11", dst_ip_addr="10.0.1.1")

        # TODO Uncomment the following two lines to read table entries from s1 and s2
        # readTableRules(p4info_helper, s1)
        # readTableRules(p4info_helper, s2)

        # Print the tunnel counters every 2 seconds
        while True:
            sleep(2)
            print('\n----- Reading tunnel counters -----')
            printCounter(p4info_helper, s1, "MyIngress.ingressTunnelCounter", 100)
            printCounter(p4info_helper, s2, "MyIngress.egressTunnelCounter", 100)
            printCounter(p4info_helper, s2, "MyIngress.ingressTunnelCounter", 200)
            printCounter(p4info_helper, s1, "MyIngress.egressTunnelCounter", 200)

    except KeyboardInterrupt:
        print(" Shutting down.")
    except grpc.RpcError as e:
        printGrpcError(e)

    ShutdownAllSwitchConnections()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/advanced_tunnel.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/advanced_tunnel.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print("\np4info file not found: %s\nHave you run 'make'?" % args.p4info)
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print("\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json)
        parser.exit(1)
    main(args.p4info, args.bmv2_json)