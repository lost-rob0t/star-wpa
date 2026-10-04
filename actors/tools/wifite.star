(actor wpa-tool-wifite
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-wifite"
   :accepts ()
   :produces ()
   :handler wpa-tool-wifite-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-wifite") (package "wifite") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
