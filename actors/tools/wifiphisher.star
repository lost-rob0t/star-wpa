(actor wpa-tool-wifiphisher
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-wifiphisher"
   :accepts ()
   :produces ()
   :handler wpa-tool-wifiphisher-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-wifiphisher") (package "wifiphisher") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
