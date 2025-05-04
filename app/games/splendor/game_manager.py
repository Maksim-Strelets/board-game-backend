import asyncio
from typing import Dict, Any, Tuple, List, Optional
import random
import time

from fastapi.encoders import jsonable_encoder

from app.games.abstract_game import AbstractGameManager
from app.serializers.game import serialize_player

from app.games.splendor import game_cards


class MoveAction:
    TAKE_DIFFERENT_GEMS = 'take_different_gems'
    TAKE_SAME_GEMS = 'take_same_gems'
    RESERVE_CARD = 'reserve_card'
    PURCHASE_CARD = 'purchase_card'
    SELECT_NOBLE = 'select_noble'
    RETURN_TOKENS = 'return_tokens'


class WebSocketGameMessage:
    NEW_TURN = 'new_turn'
    GEMS_TAKEN = 'gems_taken'
    CARD_PURCHASED = 'card_purchased'
    CARD_RESERVED = 'card_reserved'
    NOBLE_VISITED = 'noble_visited'
    GAME_OVER = 'game_over'


class GameState:
    NORMAL_TURN = 'normal_turn'
    WAITING_FOR_TOKEN_RETURN = 'waiting_for_token_return'
    WAITING_FOR_NOBLE_SELECTION = 'waiting_for_noble_selection'
    GAME_OVER = 'game_over'


class GameSettings:
    token_limit = 10
    prestige_to_win = 15
    noble_tiles_count = 5  # Total number of noble tiles in the game

    # 4 cards visible for each level
    cards_visible_per_level = 4

    # Number of tokens per gem color
    gem_tokens_for_2p = 4
    gem_tokens_for_3p = 5
    gem_tokens_for_4p = 7

    # Gold tokens
    gold_tokens = 5

    # Noble tiles to display based on player count
    noble_tiles_for_2p = 3
    noble_tiles_for_3p = 4
    noble_tiles_for_4p = 5

    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            if hasattr(self, name):
                setattr(self, name, value)


class SplendorManager(AbstractGameManager):
    """Implementation of Splendor card game logic."""

    def __init__(self, db, room, connection_manager, game_settings):
        self.is_started = False

        super().__init__(db, room, connection_manager, game_settings)
        # Ensure we have 2-4 players (based on game rules)
        if len(room.players) < 2 or len(room.players) > 4:
            raise ValueError("Splendor requires 2-4 players")

        self.game_settings = GameSettings(**game_settings)

        # Track game start time for statistics
        self.start_time = time.time()

        # Player state tracking
        self.player_gems = {}  # Will store gem tokens for each player
        self.player_reserved_cards = {}  # Will store reserved cards for each player
        self.player_purchased_cards = {}  # Will store cards purchased by each player
        self.player_nobles = {}  # Will store noble tiles acquired by each player
        self.moves_count = {player.user_id: 0 for player in room.players}
        self.turn_state = GameState.NORMAL_TURN

        # Game state
        self.gem_tokens = {}  # Available gem tokens
        self.gold_tokens = 0  # Available gold tokens (jokers)

        self.card_decks = {
            1: [],  # Level 1 cards
            2: [],  # Level 2 cards
            3: []  # Level 3 cards
        }

        self.visible_cards = {
            1: [],  # Visible level 1 cards
            2: [],  # Visible level 2 cards
            3: []  # Visible level 3 cards
        }

        self.noble_tiles = []  # Available noble tiles

    async def initialize_game(self) -> None:
        """Initialize the Splendor game state."""
        # Initialize each player's state
        for player_id in self.players:
            self.player_gems[player_id] = {
                'white': 0,  # Diamond
                'blue': 0,  # Sapphire
                'green': 0,  # Emerald
                'red': 0,  # Ruby
                'black': 0,  # Onyx
                'gold': 0  # Joker
            }
            self.player_reserved_cards[player_id] = []
            self.player_purchased_cards[player_id] = {
                'white': [],
                'blue': [],
                'green': [],
                'red': [],
                'black': []
            }
            self.player_nobles[player_id] = []

        # Set up the initial game state
        self.is_game_over = False
        self.winner = None
        self.current_player_index = 0  # First player starts

        # Generate cards, nobles, and tokens
        self._generate_cards_and_nobles()
        self._setup_tokens()
        self._deal_initial_cards()

        self.is_started = True

        # Send initial game state to all players
        for player in self.players:
            await self.connection_manager.send(self.room_id, player, {
                "type": "game_state",
                "state": jsonable_encoder(self.get_state(player)),
            })

        # Announce first player's turn
        message = {
            'type': WebSocketGameMessage.NEW_TURN,
            'player': jsonable_encoder(serialize_player(self.players[self.current_player_id])),
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

    def _generate_cards_and_nobles(self):
        """Generate the development cards and noble tiles."""
        # Initialize the card decks
        level1_cards = game_cards.level1_cards.copy()
        level2_cards = game_cards.level2_cards.copy()
        level3_cards = game_cards.level3_cards.copy()
        noble_tiles = game_cards.noble_tiles.copy()

        # Shuffle the decks
        random.shuffle(level1_cards)
        random.shuffle(level2_cards)
        random.shuffle(level3_cards)
        random.shuffle(noble_tiles)

        # Assign to game state
        self.card_decks[1] = level1_cards
        self.card_decks[2] = level2_cards
        self.card_decks[3] = level3_cards

        # Determine number of noble tiles based on player count
        player_count = len(self.players)
        if player_count == 2:
            noble_count = self.game_settings.noble_tiles_for_2p
        elif player_count == 3:
            noble_count = self.game_settings.noble_tiles_for_3p
        else:  # 4 players
            noble_count = self.game_settings.noble_tiles_for_4p

        # Select the noble tiles for this game
        self.noble_tiles = noble_tiles[:noble_count]

    def _setup_tokens(self):
        """Set up the token counts based on number of players."""
        player_count = len(self.players)

        # Determine gem token count based on player count
        if player_count == 2:
            token_count = self.game_settings.gem_tokens_for_2p
        elif player_count == 3:
            token_count = self.game_settings.gem_tokens_for_3p
        else:  # 4 players
            token_count = self.game_settings.gem_tokens_for_4p

        # Initialize gem tokens
        self.gem_tokens = {
            'white': token_count,
            'blue': token_count,
            'green': token_count,
            'red': token_count,
            'black': token_count
        }

        # Initialize gold tokens
        self.gold_tokens = self.game_settings.gold_tokens

    def _deal_initial_cards(self):
        """Deal the initial visible cards for each level."""
        # Reveal the initial cards for each level
        for level in [1, 2, 3]:
            self.visible_cards[level] = []
            for _ in range(self.game_settings.cards_visible_per_level):
                if self.card_decks[level]:
                    self.visible_cards[level].append(self.card_decks[level].pop(0))

    async def _process_move(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str], bool]:
        """Process a player's move."""
        # Verify it's the player's turn
        if str(player_id) != str(self.current_player_id):
            return False, "Not your turn", self.is_game_over

        # Game already over
        if self.is_game_over:
            return False, "Game is already over", self.is_game_over

        # Validate move data
        if 'action' not in move_data:
            return False, "Invalid move data, action required", self.is_game_over

        action = move_data['action']
        success = False
        error_message = None

        # Track move count
        self.moves_count[player_id] += 1

        # Process different action types
        if action == MoveAction.TAKE_DIFFERENT_GEMS and self.turn_state == GameState.NORMAL_TURN:
            success, error_message = await self._handle_take_different_gems(player_id, move_data)

        elif action == MoveAction.TAKE_SAME_GEMS and self.turn_state == GameState.NORMAL_TURN:
            success, error_message = await self._handle_take_same_gems(player_id, move_data)

        elif action == MoveAction.RESERVE_CARD and self.turn_state == GameState.NORMAL_TURN:
            success, error_message = await self._handle_reserve_card(player_id, move_data)

        elif action == MoveAction.PURCHASE_CARD and self.turn_state == GameState.NORMAL_TURN:
            success, error_message = await self._handle_purchase_card(player_id, move_data)

        # Handle token limit if the action was successful
        if success and sum(self.player_gems[player_id].values()) > self.game_settings.token_limit:
            self.turn_state = GameState.WAITING_FOR_TOKEN_RETURN

            # Request the player to return tokens
            await self.connection_manager.send(self.room_id, player_id, {
                "type": "token_return_required",
                "tokens_to_return": sum(self.player_gems[player_id].values()) - self.game_settings.token_limit
            })

            # Wait for token return before proceeding
            return success, error_message, self.is_game_over

        # Check for noble visits if the action was successful and involved purchasing a card
        if success and self.turn_state == GameState.NORMAL_TURN:
            eligible_nobles = self._check_noble_eligibility(player_id)

            if len(eligible_nobles) == 1:
                # Automatically award the noble
                noble_tile = eligible_nobles[0]
                await self._award_noble(player_id, noble_tile)
            elif len(eligible_nobles) > 1:
                # Player must choose which noble to receive
                self.turn_state = GameState.WAITING_FOR_NOBLE_SELECTION

                # Request the player to select a noble
                await self.connection_manager.send(self.room_id, player_id, {
                    "type": "noble_selection_required",
                    "eligible_nobles": eligible_nobles
                })

                # Wait for noble selection before proceeding
                return success, error_message, self.is_game_over

        if action == MoveAction.SELECT_NOBLE and self.turn_state == GameState.WAITING_FOR_NOBLE_SELECTION:
            success, error_message = await self.handle_noble_selection(player_id, move_data.get('noble_id'))

        elif action == MoveAction.RETURN_TOKENS and self.turn_state == GameState.WAITING_FOR_TOKEN_RETURN:
            success, error_message = await self.handle_token_return(player_id, move_data.get('tokens', {}))

        else:
            error_message = "Invalid action type or action not allowed in current game state"

        # If move was successful and we're still in normal turn state, advance to next player
        if success and self.turn_state == GameState.NORMAL_TURN:
            # Check for game end condition
            self.check_game_over()

            if not self.is_game_over:
                self.next_player()

                # Announce next player's turn
                message = {
                    'type': WebSocketGameMessage.NEW_TURN,
                    'player': jsonable_encoder(serialize_player(self.players[self.current_player_id])),
                }
                self.game_messages.append(message)
                await self.connection_manager.broadcast(self.room_id, message)

        # Broadcast updated game state to all players
        await self.broadcast_game_update()

        return success, error_message, self.is_game_over

    async def _handle_take_different_gems(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[
        bool, Optional[str]]:
        """Handle taking 3 gem tokens of different colors."""
        if 'gems' not in move_data:
            return False, "Gem selection is required"

        selected_gems = move_data['gems']

        # Validate that exactly 3 different colors are selected
        if len(selected_gems) != 3:
            return False, "You must select exactly 3 different gem colors"

        # Check that all colors are different
        if len(set(selected_gems)) != 3:
            return False, "You must select 3 different gem colors"

        # Check that all selected colors are valid
        valid_colors = ['white', 'blue', 'green', 'red', 'black']
        for color in selected_gems:
            if color not in valid_colors:
                return False, f"Invalid gem color: {color}"

        # Check if there are enough tokens of each color
        for color in selected_gems:
            if self.gem_tokens[color] <= 0:
                return False, f"No {color} tokens available"

        # Take the tokens
        for color in selected_gems:
            self.gem_tokens[color] -= 1
            self.player_gems[player_id][color] += 1

        # Notify about gems taken
        message = {
            'type': WebSocketGameMessage.GEMS_TAKEN,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'gems': selected_gems,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        return True, None

    async def _handle_take_same_gems(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Handle taking 2 gem tokens of the same color."""
        if 'gem_color' not in move_data:
            return False, "Gem color is required"

        color = move_data['gem_color']

        # Validate color
        valid_colors = ['white', 'blue', 'green', 'red', 'black']
        if color not in valid_colors:
            return False, f"Invalid gem color: {color}"

        # Check if there are at least 4 tokens of the selected color
        if self.gem_tokens[color] < 4:
            return False, f"Not enough {color} tokens available (need at least 4)"

        # Take 2 tokens
        self.gem_tokens[color] -= 2
        self.player_gems[player_id][color] += 2

        # Notify about gems taken
        message = {
            'type': WebSocketGameMessage.GEMS_TAKEN,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'gems': [color, color],
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        return True, None

    async def _handle_reserve_card(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Handle reserving a development card."""
        # Check if the player already has 3 reserved cards
        if len(self.player_reserved_cards[player_id]) >= 3:
            return False, "You cannot reserve more than 3 cards"

        # Determine if the player is reserving from the visible cards or from a deck
        from_deck = move_data.get('from_deck', False)

        card = None
        card_level = None
        card_position = None

        if from_deck:
            # Reserving from a deck
            if 'card_level' not in move_data:
                return False, "Card level is required when reserving from a deck"

            card_level = move_data['card_level']

            # Validate card level
            if card_level not in [1, 2, 3]:
                return False, "Invalid card level"

            # Check if the deck has any cards left
            if not self.card_decks[card_level]:
                return False, f"No cards left in level {card_level} deck"

            # Take the top card from the deck
            card = self.card_decks[card_level].pop(0)
        else:
            # Reserving a visible card
            if 'card_level' not in move_data or 'card_position' not in move_data:
                return False, "Card level and position are required when reserving a visible card"

            card_level = move_data['card_level']
            card_position = move_data['card_position']

            # Validate card level
            if card_level not in [1, 2, 3]:
                return False, "Invalid card level"

            # Validate card position
            if card_position < 0 or card_position >= len(self.visible_cards[card_level]):
                return False, "Invalid card position"

            # Get the card
            card = self.visible_cards[card_level][card_position]

            # Remove the card from visible cards
            self.visible_cards[card_level].pop(card_position)

            # Replace with a new card from the deck
            if self.card_decks[card_level]:
                self.visible_cards[card_level].append(self.card_decks[card_level].pop(0))

        # Add the card to the player's reserved cards
        self.player_reserved_cards[player_id].append(card)

        # Give the player a gold token if available
        if self.gold_tokens > 0:
            self.gold_tokens -= 1
            self.player_gems[player_id]['gold'] += 1

        # Notify about card reservation
        message = {
            'type': WebSocketGameMessage.CARD_RESERVED,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'card': card,
            'from_deck': from_deck,
            'card_level': card_level,
            'received_gold': self.gold_tokens > 0,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        return True, None

    async def _handle_purchase_card(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Handle purchasing a development card."""
        # Determine if the player is purchasing from visible cards or reserved cards
        from_reserved = move_data.get('from_reserved', False)

        card = None
        card_level = None
        card_position = None
        reserved_index = None

        if from_reserved:
            # Purchasing a reserved card
            if 'card_index' not in move_data:
                return False, "Card index is required when purchasing a reserved card"

            reserved_index = move_data['card_index']

            # Validate reserved index
            if reserved_index < 0 or reserved_index >= len(self.player_reserved_cards[player_id]):
                return False, "Invalid reserved card index"

            # Get the card
            card = self.player_reserved_cards[player_id][reserved_index]
        else:
            # Purchasing a visible card
            if 'card_level' not in move_data or 'card_position' not in move_data:
                return False, "Card level and position are required when purchasing a visible card"

            card_level = move_data['card_level']
            card_position = move_data['card_position']

            # Validate card level
            if card_level not in [1, 2, 3]:
                return False, "Invalid card level"

            # Validate card position
            if card_position < 0 or card_position >= len(self.visible_cards[card_level]):
                return False, "Invalid card position"

            # Get the card
            card = self.visible_cards[card_level][card_position]

        # Check if the player can afford the card
        affordable, required_payment = self._can_afford_card(player_id, card)

        if not affordable:
            return False, "You cannot afford this card"

        # Process the purchase
        if from_reserved:
            # Remove the card from reserved cards
            self.player_reserved_cards[player_id].pop(reserved_index)
        else:
            # Remove the card from visible cards
            self.visible_cards[card_level].pop(card_position)

            # Replace with a new card from the deck
            if self.card_decks[card_level]:
                self.visible_cards[card_level].append(self.card_decks[card_level].pop(0))

        # Add the card to the player's purchased cards
        self.player_purchased_cards[player_id][card['gem_color']].append(card)

        # Process payment
        for color, count in required_payment.items():
            if count > 0:
                self.player_gems[player_id][color] -= count
                if color == 'gold':
                    self.gold_tokens += count
                else:
                    self.gem_tokens[color] += count

        # Notify about card purchase
        message = {
            'type': WebSocketGameMessage.CARD_PURCHASED,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'card': card,
            'from_reserved': from_reserved,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        return True, None

    def _can_afford_card(self, player_id: int, card: Dict[str, Any]) -> Tuple[bool, Dict[str, int]]:
        """
        Check if a player can afford to purchase a card.

        Returns:
            Tuple[bool, Dict[str, int]]: Whether the player can afford the card and the required payment
        """
        # Get the player's gems and bonuses
        player_gems = self.player_gems[player_id]
        player_bonuses = self._get_player_bonuses(player_id)

        # Calculate the cost after applying bonuses
        required_payment = {
            'white': 0,
            'blue': 0,
            'green': 0,
            'red': 0,
            'black': 0,
            'gold': 0
        }

        for color, cost in card['cost'].items():
            # Calculate how many gems of this color we need to pay
            bonus_amount = player_bonuses.get(color, 0)
            required_amount = max(0, cost - bonus_amount)

            # First use regular gems
            gem_amount = min(required_amount, player_gems.get(color, 0))
            required_payment[color] = gem_amount
            required_amount -= gem_amount

            # Then use gold gems for any remaining cost
            if required_amount > 0:
                required_payment['gold'] += required_amount

        # Check if the player has enough gems
        can_afford = player_gems.get('gold', 0) >= required_payment['gold']

        for color in ['white', 'blue', 'green', 'red', 'black']:
            if player_gems.get(color, 0) < required_payment[color]:
                can_afford = False
                break

        return can_afford, required_payment

    def _get_player_bonuses(self, player_id: int) -> Dict[str, int]:
        """
        Get the gem bonuses for a player from their purchased cards.

        Returns:
            Dict[str, int]: The number of bonus gems for each color
        """
        bonuses = {
            'white': 0,
            'blue': 0,
            'green': 0,
            'red': 0,
            'black': 0
        }

        # Count the number of cards of each color
        for color in bonuses:
            bonuses[color] = len(self.player_purchased_cards[player_id][color])

        return bonuses

    def _check_noble_eligibility(self, player_id: int) -> List[Dict[str, Any]]:
        """
        Check if a player is eligible for any noble tiles.

        Returns:
            List[Dict[str, Any]]: List of noble tiles the player is eligible for
        """
        eligible_nobles = []
        player_bonuses = self._get_player_bonuses(player_id)

        for noble_idx, noble in enumerate(self.noble_tiles):
            eligible = True

            for color, required in noble['requirements'].items():
                if player_bonuses.get(color, 0) < required:
                    eligible = False
                    break

            if eligible:
                eligible_nobles.append((noble_idx, noble))

        return [noble for _, noble in eligible_nobles]

    async def _award_noble(self, player_id: int, noble: Dict[str, Any]):
        """Award a noble tile to a player."""
        # Find and remove the noble from the available nobles
        noble_idx = None
        for idx, n in enumerate(self.noble_tiles):
            if n['id'] == noble['id']:
                noble_idx = idx
                break

        if noble_idx is not None:
            # Remove the noble from available nobles
            self.noble_tiles.pop(noble_idx)

            # Add the noble to the player's nobles
            self.player_nobles[player_id].append(noble)

            # Notify about noble visit
            message = {
                'type': WebSocketGameMessage.NOBLE_VISITED,
                'player': jsonable_encoder(serialize_player(self.players[player_id])),
                'noble': noble,
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

            # Check if this noble triggers game end condition
            self.check_game_over()

    async def handle_token_return(self, player_id: int, tokens_to_return: Dict[str, int]) -> Tuple[bool, Optional[str]]:
        """Handle a player returning tokens to comply with the token limit."""
        # Validate that it's this player's turn and they need to return tokens
        if str(player_id) != str(self.current_player_id):
            return False, "Not your turn"

        if self.turn_state != GameState.WAITING_FOR_TOKEN_RETURN:
            return False, "Token return not required at this time"

        # Calculate how many tokens the player has
        current_tokens = sum(self.player_gems[player_id].values())
        tokens_to_return_count = sum(tokens_to_return.values())

        # Validate that the return amount is correct
        if current_tokens - tokens_to_return_count != self.game_settings.token_limit:
            return False, f"You must return exactly {current_tokens - self.game_settings.token_limit} tokens"

        # Validate that the player has the tokens they're trying to return
        for color, count in tokens_to_return.items():
            if self.player_gems[player_id].get(color, 0) < count:
                return False, f"You don't have {count} {color} tokens to return"

        # Process the token return
        for color, count in tokens_to_return.items():
            self.player_gems[player_id][color] -= count
            if color == 'gold':
                self.gold_tokens += count
            else:
                self.gem_tokens[color] += count

        # Return to normal turn state and advance to the next player
        self.turn_state = GameState.NORMAL_TURN
        return True, None

    async def handle_noble_selection(self, player_id: int, noble_id: str) -> Tuple[bool, Optional[str]]:
        """Handle a player selecting a noble when visited by multiple nobles."""
        # Validate that it's this player's turn and they need to select a noble
        if str(player_id) != str(self.current_player_id):
            return False, "Not your turn"

        if self.turn_state != GameState.WAITING_FOR_NOBLE_SELECTION:
            return False, "Noble selection not required at this time"

        # Find the selected noble
        selected_noble = None
        for noble in self.noble_tiles:
            if noble['id'] == noble_id:
                selected_noble = noble
                break

        if not selected_noble:
            return False, "Invalid noble selection"

        # Validate that the player is eligible for this noble
        eligible_nobles = self._check_noble_eligibility(player_id)
        noble_ids = [noble['id'] for noble in eligible_nobles]

        if noble_id not in noble_ids:
            return False, "You are not eligible for this noble"

        # Award the noble to the player
        await self._award_noble(player_id, selected_noble)

        # Return to normal turn state and advance to the next player
        self.turn_state = GameState.NORMAL_TURN
        return True, None

    def check_game_over(self) -> None:
        """Check if the game is over and determine the winner."""
        # Game is over if any player has reached 15 prestige points
        for player_id in self.players:
            prestige_points = self._calculate_prestige_points(player_id)

            if prestige_points >= self.game_settings.prestige_to_win:
                self.is_game_over = True
                self.turn_state = GameState.GAME_OVER
                self.winner = self._determine_winner()

                # Notify all players about the game over
                message = {
                    'type': WebSocketGameMessage.GAME_OVER,
                    'winner': jsonable_encoder(serialize_player(self.players[self.winner])),
                    'scores': {p_id: self._calculate_prestige_points(p_id) for p_id in self.players}
                }
                self.game_messages.append(message)
                # Don't send the broadcast here as it will be sent after the move is processed
                return

    def _determine_winner(self) -> int:
        """Determine the winner based on prestige points and tiebreakers."""
        max_points = -1
        min_cards = float('inf')
        winner_id = None

        for player_id in self.players:
            points = self._calculate_prestige_points(player_id)
            cards_count = self._count_cards(player_id)

            # If this player has more points, they're the new leader
            if points > max_points:
                max_points = points
                min_cards = cards_count
                winner_id = player_id
            # If tied on points, the player with fewer cards wins
            elif points == max_points and cards_count < min_cards:
                min_cards = cards_count
                winner_id = player_id

        return winner_id

    def _calculate_prestige_points(self, player_id: int) -> int:
        """Calculate the total prestige points for a player."""
        # Points from cards
        card_points = 0
        for color in self.player_purchased_cards[player_id]:
            for card in self.player_purchased_cards[player_id][color]:
                card_points += card.get('points', 0)

        # Points from nobles
        noble_points = sum(noble.get('points', 0) for noble in self.player_nobles[player_id])

        return card_points + noble_points

    def _count_cards(self, player_id: int) -> int:
        """Count the total number of development cards a player has purchased."""
        return sum(len(cards) for cards in self.player_purchased_cards[player_id].values())

    async def resend_pending_requests(self, user_id: int) -> None:
        """Resend any pending requests to a player."""
        if user_id == self.current_player_id:
            # If player has pending token return request
            if self.turn_state == GameState.WAITING_FOR_TOKEN_RETURN:
                current_tokens = sum(self.player_gems[user_id].values())
                tokens_to_return = current_tokens - self.game_settings.token_limit

                await self.connection_manager.send(self.room_id, user_id, {
                    "type": "token_return_required",
                    "tokens_to_return": tokens_to_return
                })

            # If player has pending noble selection request
            elif self.turn_state == GameState.WAITING_FOR_NOBLE_SELECTION:
                eligible_nobles = self._check_noble_eligibility(user_id)

                await self.connection_manager.send(self.room_id, user_id, {
                    "type": "noble_selection_required",
                    "eligible_nobles": eligible_nobles
                })

    async def resend_game_messages(self, user_id: int) -> None:
        """Resend all game messages to a player who reconnected."""
        for message in self.game_messages:
            await self.connection_manager.send(self.room_id, user_id, message)

    def get_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get current game state for sending to player.

        Returns sanitized game state with only information the player should see.

        Args:
            player_id (int): ID of the player requesting the state

        Returns:
            Dict[str, Any]: Sanitized game state
        """
        if not self.is_started:
            return None

        state = {
            # Basic game state information
            'current_player': self.current_player_id,
            'is_game_over': self.is_game_over,
            'winner': self.winner,
            'turn_state': self.turn_state if player_id == self.current_player_id else None,

            # Token supply
            'gem_tokens': self.gem_tokens.copy(),
            'gold_tokens': self.gold_tokens,

            # Card decks info
            'card_deck_counts': {level: len(deck) for level, deck in self.card_decks.items()},
            'visible_cards': self.visible_cards.copy(),

            # Noble tiles
            'noble_tiles': self.noble_tiles.copy(),

            # Player's own information
            'your_gems': self.player_gems[player_id].copy(),
            'your_reserved_cards': self.player_reserved_cards[player_id].copy(),
            'your_purchased_cards': self.player_purchased_cards[player_id].copy(),
            'your_nobles': self.player_nobles[player_id].copy(),
            'your_bonuses': self._get_player_bonuses(player_id),
            'your_prestige': self._calculate_prestige_points(player_id),

            # Information about other players
            'players': {}
        }

        # Add limited information about other players
        for pid in self.players:
            if pid != player_id:
                state['players'][pid] = {
                    'username': self.players[pid].user.username,
                    'gems': self.player_gems[pid].copy(),
                    'reserved_count': len(self.player_reserved_cards[pid]),
                    'purchased_cards': self.player_purchased_cards[pid].copy(),
                    'nobles': self.player_nobles[pid].copy(),
                    'prestige': self._calculate_prestige_points(pid),
                    'bonuses': self._get_player_bonuses(pid)
                }

        return state

    def get_game_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the completed game.

        Returns:
            Dict[str, Any]: Dictionary with game stats
        """
        if not self.is_game_over:
            return {"error": "Game is not yet complete"}

        # Calculate game duration
        game_duration = time.time() - self.start_time

        # Get final scores
        scores = {player_id: self._calculate_prestige_points(player_id) for player_id in self.players}

        # Compile player statistics
        player_stats = {}
        for player_id in self.players:
            player_bonuses = self._get_player_bonuses(player_id)

            # Count cards by level
            cards_by_level = {1: 0, 2: 0, 3: 0}
            for color in self.player_purchased_cards[player_id]:
                for card in self.player_purchased_cards[player_id][color]:
                    level = card.get('level', 1)
                    cards_by_level[level] += 1

            # Calculate points breakdown
            card_points = 0
            for color in self.player_purchased_cards[player_id]:
                for card in self.player_purchased_cards[player_id][color]:
                    card_points += card.get('points', 0)

            noble_points = sum(noble.get('points', 0) for noble in self.player_nobles[player_id])

            player_stats[player_id] = {
                'player': jsonable_encoder(serialize_player(self.players[player_id])),
                'final_score': scores[player_id],
                'points_breakdown': {
                    'card_points': card_points,
                    'noble_points': noble_points,
                    'total': scores[player_id]
                },
                'nobles_count': len(self.player_nobles[player_id]),
                'bonuses': player_bonuses,
                'cards_purchased': {
                    'total': self._count_cards(player_id),
                    'by_level': cards_by_level,
                    'by_color': {color: len(cards) for color, cards in self.player_purchased_cards[player_id].items()}
                },
                'gems_remaining': self.player_gems[player_id],
                'reserved_cards_remaining': len(self.player_reserved_cards[player_id]),
                'moves_made': self.moves_count[player_id]
            }

        # Game-wide statistics
        game_stats = {
            'duration_seconds': game_duration,
            'total_rounds': sum(self.moves_count.values()),
            'winner': jsonable_encoder(serialize_player(self.players[self.winner])),
            'winner_score': scores[self.winner],
            'scores': scores,
            'player_stats': player_stats,
            'nobles_claimed': sum(len(self.player_nobles[pid]) for pid in self.players),
            'cards_purchased': sum(self._count_cards(pid) for pid in self.players),
            'player_count': len(self.players)
        }

        return game_stats
