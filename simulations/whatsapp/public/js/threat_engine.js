/**
 * WhatsApp Web Simulation - Contacts & Conversation Data
 * Neutral standard contacts and real-life message streams.
 */

window.ContactsData = (function () {
  const CONTACTS = [
    {
      id: "chat_group",
      chat_id: "group_ncr_weekend@g.us",
      name: "Delhi Weekend Meetup",
      simulated_locality: "Koramangala",
      isGroup: true,
      sender_id: "+91 98765 43210",
      sender_name: "Aryan Kapoor",
      avatar: "assets/avatars/group.svg",
      status: "Aryan, Priya, Vikram, Rohan, Sneha...",
      unread: 2,
      lastSeen: "online",
      defaultMessages: [
        {
          id: "m_grp_1",
          is_analyst: false,
          sender_id: "+91 98765 43210",
          sender_name: "Aryan Kapoor",
          text: "Hey everyone! The farmhouse in South Delhi is booked for Saturday.",
          timestamp: "10:15 AM",
          status: "read"
        },
        {
          id: "m_grp_2",
          is_analyst: false,
          sender_id: "+91 91234 56789",
          sender_name: "Priya Sharma",
          text: "Awesome! What's the plan for music and supplies?",
          timestamp: "10:16 AM",
          status: "read"
        },
        {
          id: "m_grp_3",
          is_analyst: true,
          sender_id: "+91 99999 00000",
          sender_name: "You",
          text: "I'll handle the catering and sound system. See you guys by 7 PM.",
          timestamp: "10:18 AM",
          status: "read"
        }
      ]
    },
    {
      id: "chat_aryan",
      chat_id: "919876543210@c.us",
      name: "Aryan Kapoor",
      simulated_locality: "Jayanagar",
      isGroup: false,
      sender_id: "+91 98765 43210",
      sender_name: "Aryan Kapoor",
      phone: "+91 98765 43210",
      avatar: "assets/avatars/user1.svg",
      status: "Hey there! I am using WhatsApp.",
      unread: 1,
      lastSeen: "online",
      defaultMessages: [
        {
          id: "m_ar_1",
          is_analyst: false,
          sender_id: "+91 98765 43210",
          sender_name: "Aryan Kapoor",
          text: "Hey, are you still looking for the South Delhi score? MDMA pure crystal available. Transfer token amount on dark_supply@paytm to lock.",
          timestamp: "11:20 AM",
          status: "read"
        }
      ]
    },
    {
      id: "chat_rohit",
      chat_id: "919811122334@c.us",
      name: "Rohit (Supplier)",
      isGroup: false,
      sender_id: "+91 98111 22334",
      sender_name: "Rohit (Supplier)",
      phone: "+91 98111 22334",
      avatar: "assets/avatars/user1.svg",
      status: "Bulk supply orders only. Direct warehouse dispatch.",
      persona: "SUPPLIER",
      unread: 1,
      lastSeen: "online",
      defaultMessages: [
        {
          id: "m_roh_1",
          is_analyst: false,
          sender_id: "+91 98111 22334",
          sender_name: "Rohit (Supplier)",
          text: "Consignment of 500g MDMA crystals arrived at warehouse hub. Send token payment on supplier_rohit@icici to confirm bulk drop.",
          timestamp: "11:30 AM",
          status: "read"
        }
      ]
    },
    {
      id: "chat_vicky",
      chat_id: "919822233445@c.us",
      name: "Vicky (Courier Dispatch)",
      isGroup: false,
      sender_id: "+91 98222 33445",
      sender_name: "Vicky (Courier Dispatch)",
      phone: "+91 98222 33445",
      avatar: "assets/avatars/user1.svg",
      status: "Active courier router. Dead drops NCR.",
      persona: "COURIER_DISPATCH",
      unread: 1,
      lastSeen: "online",
      defaultMessages: [
        {
          id: "m_vic_1",
          is_analyst: false,
          sender_id: "+91 98222 33445",
          sender_name: "Vicky (Courier Dispatch)",
          text: "Package dispatch ready for dead drop pickup at Gurgaon Sector 29 pin. Share drop confirmation receipt.",
          timestamp: "11:45 AM",
          status: "read"
        }
      ]
    },
    {
      id: "chat_priya",
      chat_id: "919123456789@c.us",
      name: "Priya Sharma",
      simulated_locality: "Indiranagar",
      isGroup: false,
      sender_id: "+91 91234 56789",
      sender_name: "Priya Sharma",
      phone: "+91 91234 56789",
      avatar: "assets/avatars/user1.svg",
      status: "Busy at work",
      unread: 0,
      lastSeen: "last seen today at 01:15 PM",
      defaultMessages: [
        {
          id: "m_pr_1",
          is_analyst: false,
          sender_id: "+91 91234 56789",
          sender_name: "Priya Sharma",
          text: "Hey! Did you submit the quarterly marketing report to Rahul?",
          timestamp: "Yesterday",
          status: "read"
        },
        {
          id: "m_pr_2",
          is_analyst: true,
          sender_id: "+91 99999 00000",
          sender_name: "You",
          text: "Yes, sent it over email this morning. Let me know if revisions are needed.",
          timestamp: "Yesterday",
          status: "read"
        }
      ]
    },
    {
      id: "chat_vikram",
      chat_id: "919988776655@c.us",
      name: "Vikram Malhotra",
      simulated_locality: "Whitefield",
      isGroup: false,
      sender_id: "+91 99887 76655",
      sender_name: "Vikram Malhotra",
      phone: "+91 99887 76655",
      avatar: "assets/avatars/user1.svg",
      status: "Cyber City, Gurgaon",
      unread: 0,
      lastSeen: "online",
      defaultMessages: [
        {
          id: "m_vk_1",
          is_analyst: false,
          sender_id: "+91 99887 76655",
          sender_name: "Vikram Malhotra",
          text: "LSD Stamps and Chitta ready for pickup near Cyber Hub. Send advance token on score_vendor@ybl.",
          timestamp: "Wednesday",
          status: "read"
        }
      ]
    },
    {
      id: "chat_rohan",
      chat_id: "919555433211@c.us",
      name: "Rohan Varma",
      simulated_locality: "Rajajinagar",
      isGroup: false,
      sender_id: "+91 95554 33211",
      sender_name: "Rohan Varma",
      phone: "+91 95554 33211",
      avatar: "assets/avatars/user1.svg",
      status: "In a meeting",
      unread: 0,
      lastSeen: "last seen yesterday at 06:40 PM",
      defaultMessages: [
        {
          id: "m_ro_1",
          is_analyst: false,
          sender_id: "+91 95554 33211",
          sender_name: "Rohan Varma",
          text: "Can you share the venue location pin on Google Maps?",
          timestamp: "Yesterday",
          status: "read"
        }
      ]
    },
    {
      id: "chat_sneha",
      chat_id: "919000011223@c.us",
      name: "Sneha Gupta",
      simulated_locality: "Banashankari",
      isGroup: false,
      sender_id: "+91 90000 11223",
      sender_name: "Sneha Gupta",
      phone: "+91 90000 11223",
      avatar: "assets/avatars/user1.svg",
      status: "At the gym ",
      unread: 0,
      lastSeen: "last seen today at 09:10 AM",
      defaultMessages: [
        {
          id: "m_sn_1",
          is_analyst: false,
          sender_id: "+91 90000 11223",
          sender_name: "Sneha Gupta",
          text: "Current Account for Hawala transfer: A/C 921020048192837, IFSC: HDFC0001234. Let me know once done.",
          timestamp: "Tuesday",
          status: "read"
        }
      ]
    }
  ];

  return {
    CONTACTS
  };
})();
