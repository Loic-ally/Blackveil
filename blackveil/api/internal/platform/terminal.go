package platform

import (
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gorilla/websocket"
	"golang.org/x/crypto/ssh"
)

func (s *Server) terminal(w http.ResponseWriter, r *http.Request) {
	p := current(r)
	if p.Role != "system_admin" {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "Linux lab access is not enabled for this identity"})
		return
	}
	if r.Header.Get("Origin") != s.publicOrigin {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "request origin rejected"})
		return
	}
	if _, err := s.db.Exec(r.Context(), `INSERT INTO audit_events(tenant_id,user_id,action,object_type,object_id) VALUES($1,$2,'lab.session.requested','service','aether-linux')`, p.TenantID, p.UserID); err != nil {
		writeError(w, err)
		return
	}

	privateKey, err := os.ReadFile(s.vmSSHKeyPath)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab is not running"})
		return
	}
	signer, err := ssh.ParsePrivateKey(privateKey)
	if err != nil {
		log.Printf("Linux lab operator key is invalid: %v", err)
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab is unavailable"})
		return
	}
	hostPublicKey, err := os.ReadFile(s.vmSSHHostKeyPath)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab is not running"})
		return
	}
	pinnedHostKey, _, _, _, err := ssh.ParseAuthorizedKey(hostPublicKey)
	if err != nil {
		log.Printf("Linux lab host key is invalid: %v", err)
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab is unavailable"})
		return
	}
	client, err := ssh.Dial("tcp", s.vmSSHAddress, &ssh.ClientConfig{
		User:            "operator",
		Auth:            []ssh.AuthMethod{ssh.PublicKeys(signer)},
		HostKeyCallback: ssh.FixedHostKey(pinnedHostKey),
		Timeout:         5 * time.Second,
	})
	if err != nil {
		log.Printf("Linux lab SSH connection failed: %v", err)
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab is not running"})
		return
	}
	defer client.Close()

	session, err := client.NewSession()
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab shell is unavailable"})
		return
	}
	defer session.Close()
	input, err := session.StdinPipe()
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab shell is unavailable"})
		return
	}
	output, outputWriter := io.Pipe()
	defer output.Close()
	defer outputWriter.Close()
	session.Stdout = outputWriter
	session.Stderr = outputWriter
	if err = session.RequestPty("dumb", 24, 100, ssh.TerminalModes{ssh.ECHO: 1}); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab shell is unavailable"})
		return
	}
	if err = session.Shell(); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "Linux lab shell is unavailable"})
		return
	}

	upgrader := websocket.Upgrader{
		HandshakeTimeout: 5 * time.Second,
		ReadBufferSize:   1024,
		WriteBufferSize:  1024,
		CheckOrigin:      func(request *http.Request) bool { return request.Header.Get("Origin") == s.publicOrigin },
	}
	connection, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	defer connection.Close()
	connection.SetReadLimit(4096)

	writeDone := make(chan struct{})
	go func() {
		defer close(writeDone)
		buffer := make([]byte, 2048)
		for {
			count, readErr := output.Read(buffer)
			if count > 0 {
				_ = connection.SetWriteDeadline(time.Now().Add(10 * time.Second))
				if writeErr := connection.WriteMessage(websocket.TextMessage, buffer[:count]); writeErr != nil {
					return
				}
			}
			if readErr != nil {
				return
			}
		}
	}()

	for {
		messageType, message, readErr := connection.ReadMessage()
		if readErr != nil {
			return
		}
		if messageType != websocket.TextMessage && messageType != websocket.BinaryMessage {
			continue
		}
		if _, err = input.Write(message); err != nil {
			return
		}
		select {
		case <-writeDone:
			return
		default:
		}
	}
}
