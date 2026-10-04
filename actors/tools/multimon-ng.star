(actor wpa-tool-multimon-ng
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-multimon-ng"
   :accepts ()
   :produces ()
   :handler wpa-tool-multimon-ng-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-multimon-ng") (package "multimon-ng") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
