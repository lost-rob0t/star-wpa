(actor wpa-tool-wireless-tools
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-wireless-tools"
   :accepts ()
   :produces ()
   :handler wpa-tool-wireless-tools-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-wireless-tools") (package "wireless-tools") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
