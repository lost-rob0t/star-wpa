(actor wpa-tool-king-phisher
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-king-phisher"
   :accepts ()
   :produces ()
   :handler wpa-tool-king-phisher-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-king-phisher") (package "king-phisher") (family "network")
              (commandBoundary "operator-local-json-file"))))
