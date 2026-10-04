(require :asdf)
(unless (uiop:getenv "STARLANG_SOURCE")
  (error "Set STARLANG_SOURCE to the pinned StarLang checkout."))
(let* ((root (merge-pathnames "../" (uiop:pathname-directory-pathname *load-truename*)))
       (source (uiop:getenv "STARLANG_SOURCE")))
  (asdf:initialize-source-registry
   `(:source-registry :inherit-configuration (:tree ,(namestring root)) (:tree ,source))))
(asdf:load-system "star-wpa")
(let* ((root (asdf:system-source-directory "star-wpa"))
       (runtime (star-wpa:start-wireless-runtime)))
  (unwind-protect
       (progn
         (assert (= 64 (starlangruntime:runtime-actor-count runtime)))
         (let* ((request (namestring (merge-pathnames "tests/fixtures/listener.json" root)))
                (first (star-wpa:dispatch runtime "listener" request))
                (second (star-wpa:dispatch runtime "listener" request)))
           (assert (string= first second))
           (assert (search "wireless-network" first))
           (assert (search "0.10.1" first))
           (assert (= 2 (starlangruntime:actor-instance-invocation-count
                         (starlangruntime:resolve-actor runtime "wpa-listener")))))
         (dolist (capability '("gpsd" "kismet" "wardrive"))
           (let ((output (star-wpa:dispatch
                          runtime capability
                          (namestring (merge-pathnames (format nil "tests/fixtures/~A.json" capability) root)))))
             (assert (search "0.10.1" output))
             (assert (search "relation" output))))
         (let ((output (star-wpa:dispatch runtime "tool-wifiphisher"
                        (namestring (merge-pathnames "tests/fixtures/tool-discovery.json" root)))))
           (assert (search "wireless-tool-discovery" output))
           (assert (search "wifiphisher" output)))
         (let ((request (uiop:getenv "STAR_WPA_NATIVE_TOOL_REQUEST")))
           (when request
             (let ((output (star-wpa:dispatch runtime "tool-wifiphisher" request)))
               (assert (search "wireless-tool-execution" output))
               (assert (search "stdoutBytes" output))
               (assert (not (search "native-tool-port-fixture" output))))))
         ;; Failure crosses the real mailbox and process boundary, not a mock handler.
         (let ((failed nil))
           (handler-case
               (star-wpa:dispatch runtime "deauth" (namestring (merge-pathnames "tests/fixtures/deauth-denied.json" root)))
             (error () (setf failed t)))
           (assert failed))
         (assert (null (find-package "STAR-LANG.PROTOTYPE")))
         (format t "STAR-WPA-NATIVE-PROOF-OK~%"))
    (starlangruntime:shutdown-runtime runtime)))
