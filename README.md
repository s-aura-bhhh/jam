# Just A Minute !

A real-time buzzer system built for the **Enarrators Oratory Club** to conduct live **Just A Minute (JAM)** speaking competitions.

Designed to remain responsive even on crowded college Wi-Fi networks, the application ensures fairness, consistency, and extremely low latency.


# Performance

- **Under 50 ms latency** between button press and room lock
- **100+ concurrent WebSocket connections**
- **10 timer broadcasts per second**
- Stable performance during live competitions

---

# How It Works

### 1. Server-Authoritative State Machine

The server owns:

- Current room state
- Active speaker
- Game timer
- Buzz lock
- Speaking duration

Clients cannot modify these values.

---

### 2. Background Timer Thread

A dedicated background thread manages the competition timer.

It:

- Updates the clock independently
- Broadcasts timer updates **10 times per second**
- Never blocks incoming socket events

This keeps buzzing responsive even while the timer is running.

---

### 3. Buzz Handling

When a player presses the buzzer:

1. Server receives the event.
2. Checks if the room is unlocked.
3. Instantly locks the room.
4. Stops the timer thread.
5. Calculates the exact speaking time.

Because all decisions happen on the server, simultaneous buzzes are handled fairly without race conditions.

---

# Tech Stack

| Technology | Purpose |
|------------|---------|
| Python | Backend server |
| Flask | Web framework |
| Flask-SocketIO | Real-time WebSockets |
| HTML | Frontend |
| CSS | Styling |
| JavaScript | Client-side logic |

---

# Deployment

Hosted on **Render** with optimizations for persistent WebSocket connections and concurrent users.

