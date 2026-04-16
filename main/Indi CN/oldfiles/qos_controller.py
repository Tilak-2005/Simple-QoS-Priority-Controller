# """
# QoS Priority Controller – Ryu OpenFlow 1.3
# ===========================================
# Traffic Classification & Priority Scheduling

# Traffic Classes (highest → lowest priority):
#   PRIORITY_CRITICAL : ICMP / control traffic   (queue 0, OF priority 300)
#   PRIORITY_HIGH     : SSH, DNS, HTTP/S         (queue 1, OF priority 200)
#   PRIORITY_MEDIUM   : iperf / bulk TCP 5001    (queue 2, OF priority 100)
#   PRIORITY_LOW      : Everything else          (queue 3, OF priority  50)

# Design:
#   - packet_in → classify → install proactive flow rules per class
#   - OpenFlow match fields: eth_type, ip_proto, tcp_dst/udp_dst
#   - Output action includes set_queue for OVSDB-backed scheduling
#   - Separate MAC learning table per datapath (multi-switch safe)
#   - All events logged with timestamp for Wireshark correlation
# """

# from ryu.base import app_manager
# from ryu.controller import ofp_event
# from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
# from ryu.ofproto import ofproto_v1_3
# from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, icmp
# from ryu.lib import mac as mac_lib
# import datetime, logging

# # ─── Priority constants ───────────────────────────────────────────────
# PRIORITY_CRITICAL = 300   # ICMP / OAM
# PRIORITY_HIGH     = 200   # Interactive: SSH(22), DNS(53), HTTP(80), HTTPS(443)
# PRIORITY_MEDIUM   = 100   # Bulk TCP: iperf default port 5001
# PRIORITY_LOW      =  50   # Best-effort (default)

# QUEUE_CRITICAL = 0
# QUEUE_HIGH     = 1
# QUEUE_MEDIUM   = 2
# QUEUE_LOW      = 3

# # Hard idle/hard timeouts (seconds).  0 = permanent.
# FLOW_IDLE_TIMEOUT = 30
# FLOW_HARD_TIMEOUT =  0

# HIGH_PRIORITY_PORTS = {22, 53, 80, 443}   # TCP/UDP dst ports → HIGH
# MEDIUM_PRIORITY_PORTS = {5001, 5000}       # iperf → MEDIUM


# class QoSPriorityController(app_manager.RyuApp):
#     OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # {dpid: {eth_src: out_port}}
#         self.mac_to_port = {}
#         self.logger.setLevel(logging.DEBUG)

#     # ─── Switch handshake ─────────────────────────────────────────────

#     @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
#     def switch_features_handler(self, ev):
#         dp   = ev.msg.datapath
#         ofp  = dp.ofproto
#         parser = dp.ofproto_parser

#         # Table-miss: send to controller (priority 0)
#         match  = parser.OFPMatch()
#         actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
#                                           ofp.OFPCML_NO_BUFFER)]
#         self._add_flow(dp, 0, match, actions)
#         self.logger.info("[%s] Switch %016x connected – table-miss installed",
#                          self._ts(), dp.id)

#     # ─── Packet-in handler ────────────────────────────────────────────

#     @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
#     def packet_in_handler(self, ev):
#         msg   = ev.msg
#         dp    = msg.datapath
#         ofp   = dp.ofproto
#         parser = dp.ofproto_parser
#         in_port = msg.match['in_port']

#         pkt  = packet.Packet(msg.data)
#         eth  = pkt.get_protocol(ethernet.ethernet)
#         if eth is None:
#             return

#         # Ignore LLDP / spanning-tree multicasts
#         if eth.ethertype == 0x88cc:
#             return

#         dst_mac = eth.dst
#         src_mac = eth.src
#         dpid    = dp.id

#         # ── MAC learning ──
#         self.mac_to_port.setdefault(dpid, {})
#         self.mac_to_port[dpid][src_mac] = in_port
#         out_port = self.mac_to_port[dpid].get(dst_mac, ofp.OFPP_FLOOD)

#         # ── Traffic classification ──
#         ip_pkt  = pkt.get_protocol(ipv4.ipv4)
#         tcp_pkt = pkt.get_protocol(tcp.tcp)
#         udp_pkt = pkt.get_protocol(udp.udp)
#         icmp_pkt = pkt.get_protocol(icmp.icmp)

#         priority, queue_id, label = self._classify(ip_pkt, tcp_pkt,
#                                                     udp_pkt, icmp_pkt)
#         self.logger.info(
#             "[%s] dpid=%016x in=%d src=%s dst=%s class=%s prio=%d q=%d",
#             self._ts(), dpid, in_port, src_mac, dst_mac, label, priority, queue_id
#         )

#         # ── Build actions ──
#         if out_port != ofp.OFPP_FLOOD:
#             # Known destination → set queue + forward
#             actions = [
#                 parser.OFPActionSetQueue(queue_id),
#                 parser.OFPActionOutput(out_port),
#             ]
#             # Install proactive flow rule for this classification
#             if ip_pkt:
#                 match = self._build_match(parser, in_port, eth,
#                                           ip_pkt, tcp_pkt, udp_pkt, icmp_pkt)
#                 self._add_flow(dp, priority, match, actions,
#                                idle_timeout=FLOW_IDLE_TIMEOUT,
#                                hard_timeout=FLOW_HARD_TIMEOUT)
#         else:
#             # Flood – no queue
#             actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]

#         # ── Send packet out ──
#         data = None
#         if msg.buffer_id == ofp.OFP_NO_BUFFER:
#             data = msg.data

#         out = parser.OFPPacketOut(
#             datapath=dp,
#             buffer_id=msg.buffer_id,
#             in_port=in_port,
#             actions=actions,
#             data=data,
#         )
#         dp.send_msg(out)

#     # ─── Classification logic ─────────────────────────────────────────

#     def _classify(self, ip_pkt, tcp_pkt, udp_pkt, icmp_pkt):
#         """Return (of_priority, queue_id, label) for the given packet."""
#         if icmp_pkt is not None:
#             return PRIORITY_CRITICAL, QUEUE_CRITICAL, "CRITICAL(ICMP)"

#         if tcp_pkt is not None:
#             dport = tcp_pkt.dst_port
#             if dport in HIGH_PRIORITY_PORTS:
#                 return PRIORITY_HIGH, QUEUE_HIGH, f"HIGH(TCP:{dport})"
#             if dport in MEDIUM_PRIORITY_PORTS:
#                 return PRIORITY_MEDIUM, QUEUE_MEDIUM, f"MEDIUM(TCP:{dport})"

#         if udp_pkt is not None:
#             dport = udp_pkt.dst_port
#             if dport in HIGH_PRIORITY_PORTS:
#                 return PRIORITY_HIGH, QUEUE_HIGH, f"HIGH(UDP:{dport})"

#         return PRIORITY_LOW, QUEUE_LOW, "LOW(best-effort)"

#     # ─── Match builder ────────────────────────────────────────────────

#     def _build_match(self, parser, in_port, eth, ip_pkt,
#                      tcp_pkt, udp_pkt, icmp_pkt):
#         """Build the most specific OFPMatch for this packet."""
#         kwargs = dict(
#             in_port=in_port,
#             eth_type=0x0800,
#             ipv4_src=ip_pkt.src,
#             ipv4_dst=ip_pkt.dst,
#         )
#         if icmp_pkt:
#             kwargs['ip_proto'] = 1
#         elif tcp_pkt:
#             kwargs['ip_proto'] = 6
#             kwargs['tcp_dst'] = tcp_pkt.dst_port
#         elif udp_pkt:
#             kwargs['ip_proto'] = 17
#             kwargs['udp_dst'] = udp_pkt.dst_port

#         return parser.OFPMatch(**kwargs)

#     # ─── Flow installation helper ─────────────────────────────────────

#     def _add_flow(self, dp, priority, match, actions,
#                   idle_timeout=0, hard_timeout=0):
#         parser = dp.ofproto_parser
#         ofp    = dp.ofproto

#         inst = [parser.OFPInstructionActions(
#             ofp.OFPIT_APPLY_ACTIONS, actions)]
#         mod = parser.OFPFlowMod(
#             datapath=dp,
#             priority=priority,
#             match=match,
#             instructions=inst,
#             idle_timeout=idle_timeout,
#             hard_timeout=hard_timeout,
#             flags=ofp.OFPFF_SEND_FLOW_REM,
#         )
#         dp.send_msg(mod)
#         self.logger.debug("[%s] Flow installed prio=%d match=%s",
#                           self._ts(), priority, match)

#     # ─── Utility ──────────────────────────────────────────────────────

#     @staticmethod
#     def _ts():
#         return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet


class QoSPriorityController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(QoSPriorityController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions)]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=30
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Default rule → send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
        self.add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        dst = eth.dst
        src = eth.src

        # Learn MAC
        self.mac_to_port[dpid][src] = in_port

        # Decide output port
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        # 🔥 QoS classification
        queue_id = 3  # default LOW

        for p in pkt.protocols:
            if hasattr(p, 'proto'):
                if p.proto == 1:  # ICMP
                    queue_id = 0
                elif p.proto == 6:  # TCP
                    if hasattr(p, 'dst_port'):
                        if p.dst_port == 80:
                            queue_id = 1
                        elif p.dst_port == 5001:
                            queue_id = 2

        actions = [
            parser.OFPActionSetQueue(queue_id),
            parser.OFPActionOutput(out_port)
        ]

        match = parser.OFPMatch(
            in_port=in_port,
            eth_dst=dst
        )

        if out_port != ofproto.OFPP_FLOOD:
            self.add_flow(datapath, 100, match, actions)

        # Send packet out
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data
        )
        datapath.send_msg(out)