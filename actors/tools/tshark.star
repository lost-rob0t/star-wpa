(actor wpa-tool-tshark
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-tshark"
   :accepts ()
   :produces ()
   :handler wpa-tool-tshark-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-tshark") (package "tshark") (family "network")
              (commandBoundary "operator-local-json-file"))))
