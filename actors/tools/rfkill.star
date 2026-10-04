(actor wpa-tool-rfkill
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-rfkill"
   :accepts ()
   :produces ()
   :handler wpa-tool-rfkill-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-rfkill") (package "rfkill") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
