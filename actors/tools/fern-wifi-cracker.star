(actor wpa-tool-fern-wifi-cracker
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-fern-wifi-cracker"
   :accepts ()
   :produces ()
   :handler wpa-tool-fern-wifi-cracker-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-fern-wifi-cracker") (package "fern-wifi-cracker") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
