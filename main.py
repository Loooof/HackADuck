from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
from db import DB

PORT = 60000
app = Flask(__name__)
CORS(app)
db = DB("game_database.db")

# Handles drawing =======================================
socketio = SocketIO(app, cors_allowed_origins="*")
@socketio.on('draw')
def handle_draw(data):
    emit('draw', data, broadcast=True)

# Handles drawing =======================================



@app.route('/createGame', methods=["POST"])
def createRoom():
    username = request.headers.get("username")

    if not username:
        return {"error": "Username is required"}, 400

    # Insert a new game
    gameQuery = "INSERT INTO Game (theme, game_status, start_time) VALUES (?, ?, ?)"
    startTime = datetime.now().isoformat()
    gameID = db.insertAndFetch(gameQuery, ("Default", "drawing", startTime))
    
    if gameID is None:
        return {"error": "Failed to create game"}, 500  # Handle case where ID is None

    # Insert the new player into the Player table
    playerQuery = "INSERT INTO Player (player_name, role, game_id) VALUES (?, ?, ?)"
    role = "drawer"  # Assign a default role, modify as needed based on your logic
    playerID = db.insertAndFetch(playerQuery, (username, role, gameID))

    if playerID is None:
        return {"error": "Failed to create player"}, 500  # Handle player insertion failure

    # # Link player to game id using prompt table
    # promptQuery = "INSERT INTO Prompt (player_id, game_id, main_prompt, side_prompt) VALUES (?, ?, ?, ?)"
    # mainPrompt = "Main prompt text"
    # sidePrompt = "Secondary prompt"

    # # Insert the prompt for the new game
    # if db.insert(promptQuery, (playerID, gameID, mainPrompt, sidePrompt)) is None:
    #     return {"error": "Failed to create prompt"}, 500  # Handle prompt insertion failure

    return {"gameID": gameID, "playerID": playerID}, 200



@app.route("/joinGame", methods=["POST"])
def joinGame():
    username = request.headers.get("username")
    gameID = request.json.get("gameID")

    if not username:
        return {"error": "Username is required"}, 400
    
    if not gameID:
        return {"error": "Game ID is required"}, 400
    
    # Check if the game exists
    gameExistsQuery = "SELECT COUNT(*) FROM Game WHERE game_id = ?"
    gameExists = db.select(gameExistsQuery, (gameID,))

    if gameExists is None or gameExists[0][0] == 0:
        return {"error": "Game does not exist"}, 404
    # Check if the game exists and how many players are in it
    playerCountQuery = "SELECT COUNT(*) FROM Player WHERE game_id = ?"
    currentPlayerCount = db.select(playerCountQuery, (gameID,))

    if currentPlayerCount is None or currentPlayerCount[0][0] >= 5:
        return {"error": "Game is full or does not exist"}, 400

    # Insert the new player into the Player table
    playerQuery = "INSERT INTO Player (player_name, role, game_id) VALUES (?, ?, ?)"
    role = "drawer"  # Assign a default role; modify as needed based on your logic
    playerID = db.insertAndFetch(playerQuery, (username, role, gameID))

    if playerID is None:
        return {"error": "Failed to create player"}, 500  # Handle player insertion failure
    socketio.emit('player_update', {'username': username, 'gameID': gameID}, room=gameID)
    return {"gameID": gameID, "playerID": playerID, "username": username}, 200

@app.route("/readyup", methods=["POST"])
def readyUp():
    playerID = request.json.get("playerID")
    gameID = request.json.get("gameID")

    if not playerID or not gameID:
        return {"error": "playerID and gameID are required"}, 400

    readyQuery = "UPDATE Player SET is_ready = ? WHERE player_id = ? and game_id = ?"
    if db.update(readyQuery, (True, playerID, gameID)) == 0:
        return {"error": "Failed to update ready status or player not found"}, 404
    
    checkReadyQuery = "SELECT COUNT(*) FROM PLAYER WHERE game_id = ? and is_ready = FALSE"
    unreadyCount = db.select(checkReadyQuery, (gameID,))
    
    if unreadyCount and unreadyCount[0][0] == 0:
        print("Start game!")
        socketio.emit('game_start', room=gameID)  # Emit to all players in this game
        return {"message": "All players are ready. Game started!"}, 200
    return {"message": "Player is ready. Waiting for others."}, 200


@socketio.on('join')
def handle_join(data):
    gameID = data['gameID']
    join_room(gameID)  # Join the room corresponding to the gameID
    emit('player_update', {'players': get_players(gameID)}, room=gameID)  # Send current players

def get_players(gameID):
    playersQuery = "SELECT player_name FROM Player WHERE game_id = ?"
    players = db.select(playersQuery, (gameID,))
    return [player[0] for player in players]


@socketio.on("ready")
def handleReady(data):
    gameID = data['gameID']
    if gameID in ready_players:
        ready_players[gameID].append(request.sid)

# Handle theme votes
THEMES = ["random", "halloween", "christmas", "easter"]
gameVotes = {}
@socketio.on('vote')
def handle_vote(data):
    game_id = data["gameID"]
    player_id = data["playerID"]
    theme = data["theme"]

    if game_id not in gameVotes:
        socketio.emit("error", {"message": "Voting not started."})
        return

    gameVotes[game_id]["votes"][player_id] = theme
    total_votes = len(gameVotes[game_id]["votes"])

    # Check if all players have voted
    if total_votes >= gameVotes[game_id]["total_players"]:
        # Calculate winning theme (here, a simple count of votes)
        theme_counts = {}
        for vote in gameVotes[game_id]["votes"].values():
            theme_counts[vote] = theme_counts.get(vote, 0) + 1
        winning_theme = max(theme_counts, key=theme_counts.get)
        socketio.emit("vote_result", {"theme": winning_theme}, room=game_id)
        print("votes", winning_theme)
        del gameVotes[game_id]  # Reset votes
    emit("vote_update", {"votes": total_votes}, room=game_id)
if __name__ == "__main__":
    socketio.run(app,port=PORT)