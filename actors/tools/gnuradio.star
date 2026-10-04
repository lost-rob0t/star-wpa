(actor wpa-tool-gnuradio
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-gnuradio"
   :accepts ()
   :produces ()
   :handler wpa-tool-gnuradio-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-gnuradio") (package "gnuradio") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
