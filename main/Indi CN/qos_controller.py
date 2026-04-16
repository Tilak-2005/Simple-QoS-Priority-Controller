# from ryu.base import app_manager
# from ryu.controller import ofp_event
# from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
# from ryu.ofproto import ofproto_v1_3
# from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, icmp

# PRIORITY_CRITICAL = 300
# PRIORITY_HIGH     = 200
# PRIORITY_MEDIUM   = 100
# PRIORITY_LOW      = 50

# QUEUE_CRITICAL = 0
# QUEUE_HIGH     = 1
# QUEUE_MEDIUM   = 2
# QUEUE_LOW      = 3


# class QoSPriorityController(app_manager.RyuApp):
#     OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.mac_to_port = {}

#     def add_flow(self, datapath, priority, match, actions):
#         parser = datapath.ofproto_parser
#         ofproto = datapath.ofproto

#         inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
#         mod = parser.OFPFlowMod(
#             datapath=datapath,
#             priority=priority,
#             match=match,
#             instructions=inst,
#         )
#         datapath.send_msg(mod)

#     @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
#     def switch_features_handler(self, ev):
#         dp = ev.msg.datapath
#         parser = dp.ofproto_parser
#         ofproto = dp.ofproto

#         match = parser.OFPMatch()
#         actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
#         self.add_flow(dp, 0, match, actions)

#     @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
#     def packet_in_handler(self, ev):
#         msg = ev.msg
#         dp = msg.datapath
#         parser = dp.ofproto_parser
#         ofproto = dp.ofproto

#         dpid = dp.id
#         self.mac_to_port.setdefault(dpid, {})

#         in_port = msg.match['in_port']
#         pkt = packet.Packet(msg.data)
#         eth = pkt.get_protocol(ethernet.ethernet)

#         if eth.ethertype == 0x88cc:
#             return

#         dst = eth.dst
#         src = eth.src

#         self.mac_to_port[dpid][src] = in_port
#         out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)

#         ip_pkt = pkt.get_protocol(ipv4.ipv4)
#         tcp_pkt = pkt.get_protocol(tcp.tcp)
#         udp_pkt = pkt.get_protocol(udp.udp)
#         icmp_pkt = pkt.get_protocol(icmp.icmp)

#         # Classification
#         if icmp_pkt:
#             queue = QUEUE_CRITICAL
#             prio = PRIORITY_CRITICAL

#         elif tcp_pkt:
#             if tcp_pkt.dst_port in {80, 443}:
#                 queue = QUEUE_HIGH
#                 prio = PRIORITY_HIGH
#             elif tcp_pkt.dst_port in {5001}:
#                 queue = QUEUE_MEDIUM
#                 prio = PRIORITY_MEDIUM
#             else:
#                 queue = QUEUE_LOW
#                 prio = PRIORITY_LOW

#         elif udp_pkt:
#             queue = QUEUE_LOW
#             prio = PRIORITY_LOW

#         else:
#             queue = QUEUE_LOW
#             prio = PRIORITY_LOW

#         actions = [
#             parser.OFPActionSetQueue(queue),
#             parser.OFPActionOutput(out_port)
#         ]

#         if out_port != ofproto.OFPP_FLOOD and ip_pkt:
#             match = parser.OFPMatch(
#                 in_port=in_port,
#                 eth_type=0x0800,
#                 ipv4_src=ip_pkt.src,
#                 ipv4_dst=ip_pkt.dst,
#             )
#             self.add_flow(dp, prio, match, actions)

#         out = parser.OFPPacketOut(
#             datapath=dp,
#             buffer_id=msg.buffer_id,
#             in_port=in_port,
#             actions=actions,
#             data=msg.data,
#         )
#         dp.send_msg(out)


from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, icmp

PRIORITY_CRITICAL = 300
PRIORITY_HIGH     = 200
PRIORITY_MEDIUM   = 100
PRIORITY_LOW      = 50

QUEUE_CRITICAL = 0
QUEUE_HIGH     = 1
QUEUE_MEDIUM   = 2
QUEUE_LOW      = 3


class QoSPriorityController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(QoSPriorityController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    def add_flow(self, datapath, priority, match, actions):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        parser = dp.ofproto_parser
        ofproto = dp.ofproto

        # Default rule: send unknown packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
        self.add_flow(dp, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        parser = dp.ofproto_parser
        ofproto = dp.ofproto

        dpid = dp.id
        self.mac_to_port.setdefault(dpid, {})

        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Ignore LLDP
        if eth.ethertype == 0x88cc:
            return

        dst = eth.dst
        src = eth.src

        # Learn MAC
        self.mac_to_port[dpid][src] = in_port
        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)

        # Extract protocols
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        udp_pkt = pkt.get_protocol(udp.udp)
        icmp_pkt = pkt.get_protocol(icmp.icmp)

        # ─── QoS Classification ─────────────────────

        if icmp_pkt:
            queue = QUEUE_CRITICAL
            prio = PRIORITY_CRITICAL

        elif tcp_pkt:
            if tcp_pkt.dst_port in {80, 443, 8080}:   # ✅ FIXED
                queue = QUEUE_HIGH
                prio = PRIORITY_HIGH
            elif tcp_pkt.dst_port == 5001:
                queue = QUEUE_MEDIUM
                prio = PRIORITY_MEDIUM
            else:
                queue = QUEUE_LOW
                prio = PRIORITY_LOW

        else:
            queue = QUEUE_LOW
            prio = PRIORITY_LOW

        actions = [
            parser.OFPActionSetQueue(queue),
            parser.OFPActionOutput(out_port)
        ]

        # Install flow rule (only for IP traffic)
        if out_port != ofproto.OFPP_FLOOD and ip_pkt:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_type=0x0800,
                ipv4_src=ip_pkt.src,
                ipv4_dst=ip_pkt.dst
            )
            self.add_flow(dp, prio, match, actions)

        # Send packet out
        out = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data
        )
        dp.send_msg(out)