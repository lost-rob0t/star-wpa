(actor wpa-tool-airgeddon
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-airgeddon"
   :accepts ()
   :produces ()
   :handler wpa-tool-airgeddon-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-airgeddon") (package "airgeddon") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
