export interface RealtimeConnection {
  close(): void;
}

/**
 * ctx.realtime — lifecycle-managed connections (WebSocket / polling).
 * Plugins hand the service a connection factory; the runtime closes every
 * connection when the Cordis context stops (logout, workspace switch,
 * permission downgrade), so plugin timers and sockets cannot leak.
 */
export class RealtimeService {
  private connections = new Map<string, RealtimeConnection>();

  open(key: string, connect: () => RealtimeConnection): RealtimeConnection {
    this.close(key);
    const connection = connect();
    this.connections.set(key, connection);
    return connection;
  }

  close(key: string): void {
    const connection = this.connections.get(key);
    if (connection) {
      try {
        connection.close();
      } catch {
        /* an already-closed connection must not fail disposal */
      }
      this.connections.delete(key);
    }
  }

  closeAll(): void {
    for (const key of [...this.connections.keys()]) this.close(key);
  }

  connectionCount(): number {
    return this.connections.size;
  }
}
