(actor wpa-tool-bettercap
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-bettercap"
   :accepts ()
   :produces ()
   :handler wpa-tool-bettercap-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-bettercap") (package "bettercap") (family "network")
              (commandBoundary "operator-local-json-file"))))
