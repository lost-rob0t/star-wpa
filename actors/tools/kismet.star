(actor wpa-tool-kismet
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-kismet"
   :accepts ()
   :produces ()
   :handler wpa-tool-kismet-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-kismet") (package "kismet") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
