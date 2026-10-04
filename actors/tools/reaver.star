(actor wpa-tool-reaver
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-reaver"
   :accepts ()
   :produces ()
   :handler wpa-tool-reaver-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-reaver") (package "reaver") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
