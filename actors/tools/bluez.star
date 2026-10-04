(actor wpa-tool-bluez
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-bluez"
   :accepts ()
   :produces ()
   :handler wpa-tool-bluez-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-bluez") (package "bluez") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
