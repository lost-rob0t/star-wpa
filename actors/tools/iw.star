(actor wpa-tool-iw
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-iw"
   :accepts ()
   :produces ()
   :handler wpa-tool-iw-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-iw") (package "iw") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
