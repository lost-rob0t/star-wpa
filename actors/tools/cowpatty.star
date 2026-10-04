(actor wpa-tool-cowpatty
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-cowpatty"
   :accepts ()
   :produces ()
   :handler wpa-tool-cowpatty-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-cowpatty") (package "cowpatty") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
