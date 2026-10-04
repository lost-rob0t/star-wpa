(actor wpa-tool-ubertooth
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-ubertooth"
   :accepts ()
   :produces ()
   :handler wpa-tool-ubertooth-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-ubertooth") (package "ubertooth") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
