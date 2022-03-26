/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4 = 0x800;

/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/
/*  根据字段的长度信息，定义数据包头 */
typedef bit<9>  egressSpec_t; 
typedef bit<48> macAddr_t;     
typedef bit<32> ip4Addr_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    /* empty */
}

struct headers {
    ethernet_t   ethernet;
    ipv4_t       ipv4;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/
/* MyParser的作用是解析数据包，提取包头 */
parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        /* TODO: add parser logic */
        //可以填充ethernet_t和ipv4_t字段
        transition parse_ethernet;    //转移到parse_ethernet状态
         
    }
    state parse_ethernet{
        packet.extract(hdr.ethernet);//根据定义的数据结构提取以太网包头
        transition select(hdr.ethernet.etherType){
            //根据协议类型选择下一个状态
            0x0800：parse_ipv4; //如果是0x0800,则转移到parse_ipv4状态
            defualt:accept; //默认是接受，转移到下一步处理
        
        }
        state parse_ipv4{
            packet.extract(hdr.ipv4); //提取ip包头
            transition accept;
        }
    }
}


/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {  }
}


/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {
    action drop() {
        mark_to_drop(standard_metadata); //内置函数，将当前数据包标记为即将丢弃的数据包
    }

    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {
        /* TODO: fill out code in action body */
        standard_metadata.egress_spec = port;  //
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;//原数据包的源地址改为目的地址
        hdr.ethernet.dstAddr = dstAddr;//目的地址改为传入的新的地址
         hdr.ipv4.ttl = hdr.ipv4.ttl - 1;       //ttl递减
    }

    table ipv4_lpm {
        key = {         //流表拥有的匹配域
            hdr.ipv4.dstAddr: lpm;   // 匹配字段是数据包头的ip目的地址
        }
        actions = {     //流表拥有的动作类型集合
            ipv4_forward;   //自行定义的转发动作
            drop;        //丢弃动作
            NoAction;    //空动作
        }
        size = 1024;     //流表可以容纳多少流表项
        default_action = NoAction();    // 默认动作丢弃动作
    }

    apply {
        /* TODO: fix ingress control logic
         *  - ipv4_lpm should be applied only when IPv4 header is valid
         */
         /*ipv4 case*/
        if (hdr.ipv4.isValid()) {
        ipv4_lpm.apply();
        }
    }
}
//MyIngress的作用是输出处理
/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply {  }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
     apply {
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}


/*************************************************************************
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        /* TODO: add deparser logic */
        packet.emit(hdr.ethernet);  
        packet.emit(hdr.ipv4);
    }
}
//MyDeparser是逆解析器
/*************************************************************************
***********************  S W I T C H  *******************************
*************************************************************************/

V1Switch(
MyParser(),
MyVerifyChecksum(),
MyIngress(),
MyEgress(),
MyComputeChecksum(),
MyDeparser()
) main;