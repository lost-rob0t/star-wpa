(actor wpa-tool-aircrack-ng
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-aircrack-ng"
   :accepts ()
   :produces ()
   :handler wpa-tool-aircrack-ng-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-aircrack-ng") (package "aircrack-ng") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
