(actor wpa-tool-redfang
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-redfang"
   :accepts ()
   :produces ()
   :handler wpa-tool-redfang-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-redfang") (package "redfang") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
