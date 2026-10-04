(actor wpa-tool-wireshark
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-wireshark"
   :accepts ()
   :produces ()
   :handler wpa-tool-wireshark-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-wireshark") (package "wireshark") (family "network")
              (commandBoundary "operator-local-json-file"))))
