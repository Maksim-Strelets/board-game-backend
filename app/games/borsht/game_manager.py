import asyncio
from typing import Dict, Any, Tuple, List, Optional
import random
import time

from fastapi.encoders import jsonable_encoder

from app.games.abstract_game import AbstractGameManager
from app.serializers.game import serialize_player

from app.games.borsht import game_cards


class MoveAction:
    ADD_INGREDIENT = 'add_ingredient'
    DRAW_CARDS = 'draw_cards'
    PLAY_SPECIAL = 'play_special'
    EXCHANGE_INGREDIENTS = 'exchange_ingredients'
    FREE_MARKET_REFRESH = 'free_market_refresh'
    SKIP = 'skip'


class WebSocketGameMessage:
    NEW_TURN = 'new_turn'
    RECIPE_COMPLETED = 'recipe_completed'
    INGREDIENT_ADDED = 'ingredient_added'
    CARDS_DRAWN = 'cards_drawn'
    SPECIAL_PLAYED = 'special_played'
    CARDS_FROM_DISCARD_SELECTED = 'cards_from_discard_selected'
    MARKET_CARDS_TAKEN = 'market_cards_taken'
    SPECIAL_EFFECT = 'special_effect'
    CARD_STOLEN = 'card_stolen'
    DEFENSE_SUCCESSFUL = 'defense_successful'
    BORSHT_CARD_DISCARDED = 'borsht_card_discarded'
    CARDS_FROM_HAND_DISCARDED = 'cards_from_hand_discarded'
    CHILI_PEPPER_EFFECT_APPLIED = 'chili_pepper_effect_applied'
    CARDS_FROM_MARKET_DISCARDED = 'cards_from_market_discarded'
    MARKET_CARDS_ADDED = 'market_cards_added'
    INGREDIENTS_EXCHANGED = 'ingredients_exchanged'


class GameState:
    NORMAL_TURN = 'normal_turn'
    WAITING_FOR_DEFENSE = 'waiting_for_defense'
    WAITING_FOR_SELECTION = 'waiting_for_selection'
    WAITING_FOR_DISCARD = 'waiting_for_discard'
    WAITING_FOR_EXCHANGE = 'waiting_for_exchange'
    GAME_OVER = 'game_over'
    

class GameSettings:
    general_player_select_timeout = 300
    cards_to_draw = 2
    borscht_recipes_select_count = 3
    disposable_shkvarka_count = 0
    permanent_shkvarka_count = 0
    market_capacity = 8
    player_hand_limit = 8
    player_start_hand_size = 5
    market_exchange_tax = 0
    extra_cards_allowed = True
    market_base_capacity = 8
    
    # special cards
    olive_oil_look_count = 5
    olive_oil_select_count = 2
    cinnamon_select_count = 1
    ginger_select_count = 2
    chili_pepper_discard_count = 1
    smetana_count_for_defence = 1

    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            if self.__getattribute__(name) is not None:
                self.__setattr__(name, value)

        self.market_base_capacity = self.market_capacity


class BorshtManager(AbstractGameManager):
    """Implementation of Borsht card game logic."""
    def __init__(self, db, room, connection_manager, game_settings):
        self.is_started = False

        super().__init__(db, room, connection_manager, game_settings)
        # Ensure we have 2-5 players (based on game rules)
        if len(room.players) < 2 or len(room.players) > 5:
            raise ValueError("Borsht requires 2-5 players")

        self.game_settings = GameSettings(**game_settings)

        # Track game start time for statistics
        self.start_time = time.time()

        # Player state tracking
        self.player_recipes = {}  # Will store the recipe card for each player
        self.player_borsht = {}  # Will store ingredients in each player's borsht
        self.player_hands = {}  # Will store cards in each player's hand
        self.moves_count = {player.user_id: 0 for player in room.players}
        self.turn_state = GameState.NORMAL_TURN

        # Game state
        self.market = []  # Cards available in the market
        self.deck = []  # Main ingredient deck
        self.discard_pile = []  # Discard pile
        self.pending_shkvarkas = []

        # Special states tracking
        self.recipes_revealed = False  # If recipes are revealed due to "Talkative Cook" shkvarka
        self.game_ending = False  # Flag to indicate we're in the final round
        self.first_finisher = None  # Player who completed their recipe first

        # "shkvarka" cards (Shkvarky) active effects
        self.active_shkvarkas = []  # List of active permanent shkvarka effects

    async def initialize_game(self) -> None:
        """Initialize the Borsht game state."""
        # Initialize each player's state
        for player_id in self.players:
            self.player_borsht[player_id] = []  # Empty borsht
            self.player_hands[player_id] = []  # Empty hand
            self.player_recipes[player_id] = None  # No recipe yet

        # Set up the initial game state
        self.is_game_over = False
        self.winner = None
        self.current_player_index = 0  # First player starts

        # Generate deck, deal cards and set up market
        self._generate_deck()
        await self._deal_initial_cards()
        await self._handle_market_refill()
        self._add_shkvarkas()

        self.is_started = True
        for player in self.players:
            await self.connection_manager.send(self.room_id, player, {
                "type": "game_state",
                "state": jsonable_encoder(self.get_state(player)),
            })

        message = {
            'type': WebSocketGameMessage.NEW_TURN,
            'player': jsonable_encoder(serialize_player(self.players[self.current_player_id])),
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

    def _generate_deck(self):
        """Generate the ingredient deck based on game rules."""
        # This would typically come from a database, but for this example,
        # we'll define it directly in code based on the game rulebook
        self.deck = game_cards.base_cards.copy()
        self.recipes = game_cards.recipes.copy()

        # Shuffle the deck (we would use a proper shuffle in production)
        random.shuffle(self.deck)
        random.shuffle(self.recipes)

    async def _deal_initial_cards(self):
        """Deal initial cards to players and let them choose recipes simultaneously."""
        # Deal 5 cards to each player
        for player_id in self.players:
            self.player_hands[player_id] = self.deck[:self.game_settings.player_start_hand_size]
            self.deck = self.deck[self.game_settings.player_start_hand_size:]

        # Dictionary to store recipe options for each player
        player_recipe_options = {}

        # Assign recipe options to each player (3 options per player)
        for player_id in self.players:
            player_recipe_options[player_id] = self.recipes[:self.game_settings.borscht_recipes_select_count]
            self.recipes = self.recipes[self.game_settings.borscht_recipes_select_count:]

        # Create recipe selection tasks for all players simultaneously
        selection_tasks = []
        for player_id, recipe_options in player_recipe_options.items():
            # Prepare request data
            request_data = {
                'recipe_options': recipe_options
            }

            # Create task for recipe selection request
            task = asyncio.create_task(
                self._request_to_player(
                    player_id=player_id,
                    request_type='recipe_selection',
                    request_data=request_data,
                    timeout=self.game_settings.general_player_select_timeout,
                )
            )

            selection_tasks.append((player_id, recipe_options, task))

        # Wait for all recipe selections (or timeouts) to complete
        for player_id, recipe_options, task in selection_tasks:
            try:
                # Wait for the player's response
                response = await task

                # Check if player responded in time
                if response.get('timed_out', False):
                    # If timed out, randomly select a recipe
                    selected_recipe = random.choice(recipe_options)
                else:
                    # Get player's selected recipe
                    selected_recipe_id = response.get('selected_recipe')

                    # Find the selected recipe
                    selected_recipe = None
                    for recipe in recipe_options:
                        if recipe['id'] == selected_recipe_id:
                            selected_recipe = recipe
                            break

                    # If invalid selection, choose randomly
                    if selected_recipe is None:
                        selected_recipe = random.choice(recipe_options)

                # Assign the selected recipe to the player
                self.player_recipes[player_id] = selected_recipe

            except Exception as e:
                # Log any errors and fallback to random selection
                print(f"Error during recipe selection for player {player_id}: {e}")
                selected_recipe = random.choice(recipe_options)
                self.player_recipes[player_id] = selected_recipe

            await self.connection_manager.send(self.room_id, player_id, {
                'type': 'recipe_selected',
                'recipe': selected_recipe['name']
            })

    def _add_shkvarkas(self):
        if self.game_settings.disposable_shkvarka_count:
            random.shuffle(game_cards.skvarkas_disposable)
            self.deck.extend(game_cards.skvarkas_disposable.copy()[:self.game_settings.disposable_shkvarka_count])
        if self.game_settings.permanent_shkvarka_count:
            random.shuffle(game_cards.skvarkas_permanent)
            self.deck.extend(game_cards.skvarkas_permanent.copy()[:self.game_settings.permanent_shkvarka_count])

        random.shuffle(self.deck)

    async def _process_move(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str], bool]:
        """Process a player's move."""
        # Verify it's the player's turn
        if str(player_id) != str(self.current_player_id):
            return False, "Not your turn", self.is_game_over

        # Game already over
        if self.is_game_over:
            return False, "Game is already over", self.is_game_over

        # Can't target the player who completed their recipe first
        if self.first_finisher is not None and move_data.get('target_player') == self.first_finisher:
            return False, "Cannot target a player who has completed their recipe", self.is_game_over

        # Validate move data
        if 'action' not in move_data:
            return False, "Invalid move data, action required", self.is_game_over

        action = move_data['action']
        success = False
        error_message = None
        is_move_continues = False

        # Track move count
        self.moves_count[player_id] += 1

        # Process different action types
        if action == MoveAction.ADD_INGREDIENT and self.turn_state == GameState.NORMAL_TURN:
            # Add an ingredient to the player's borsht
            success, error_message = await self._handle_add_ingredient(player_id, move_data)

        elif action == MoveAction.DRAW_CARDS and self.turn_state == GameState.NORMAL_TURN:
            # Draw 2 cards from the deck
            success, error_message = await self._handle_draw_cards(player_id)

        elif action == MoveAction.PLAY_SPECIAL and self.turn_state == GameState.NORMAL_TURN:
            # Play a special ingredient card for its effect
            success, error_message, is_move_continues = await self._handle_special_ingredient(player_id, move_data)

        elif action == MoveAction.EXCHANGE_INGREDIENTS and self.turn_state in [GameState.NORMAL_TURN, GameState.WAITING_FOR_EXCHANGE]:
            # Exchange ingredients with the market
            success, error_message = await self._handle_exchange(player_id, move_data)

        elif action == MoveAction.SKIP and self.turn_state == GameState.WAITING_FOR_EXCHANGE:
            success, error_message = True, None

        elif action == MoveAction.FREE_MARKET_REFRESH:
            # Refresh the market
            success, error_message = await self._handle_free_market_refresh()
            await self.broadcast_game_update()
            is_move_continues = True

        elif self.game_state in [GameState.WAITING_FOR_DEFENSE, GameState.WAITING_FOR_DISCARD]:
            error_message = "Can't make move, while waiting for response"
            is_move_continues = True

        else:
            error_message = "Invalid action type"
            is_move_continues = True

        if is_move_continues:
            await self._process_shkvarkas()
            return success, error_message, self.is_game_over

        # Check hand limit and ask player to discard if needed
        limit_success, updated_hand = await self._handle_hand_limit(player_id)
        if limit_success:
            self.player_hands[player_id] = updated_hand

        await self._process_shkvarkas()

        # Check if player has completed their recipe
        recipe_completed = self._check_recipe_completion(player_id)

        # If player completed recipe and it's the first to do so
        if recipe_completed and self.first_finisher is None:
            self.first_finisher = player_id
            self.game_ending = True
            message = {
                'type': WebSocketGameMessage.RECIPE_COMPLETED,
                'player': jsonable_encoder(serialize_player(self.players[player_id])),
                'is_first': True
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

        # If move was successful and game not over, advance to next player
        if success and not self.is_game_over:
            self.next_player()
            self.turn_state = GameState.NORMAL_TURN

            self.is_game_over, self.winner = self.check_game_over()

            message = {
                'type': WebSocketGameMessage.NEW_TURN,
                'player': jsonable_encoder(serialize_player(self.players[self.current_player_id])),
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

        await self.broadcast_game_update()

        return success, error_message, self.is_game_over

    async def _handle_free_market_refresh(self) -> tuple[bool, Optional[str]]:
        if not self._is_market_free_refresh_available():
            return False, "Free market refresh not available"

        await self._handle_market_refresh()

        return True, None

    async def _get_cards_from_deck(self, count) -> list[dict]:
        cards = []
        while len(cards) < count:
            if len(self.deck) == 0:
                await self._reshuffle_discard()
                if len(self.deck) == 0:
                    return cards

            card = self.deck.pop(0)
            if card.get('type') == 'shkvarka':
                self.pending_shkvarkas.append(card)
            else:
                cards.append(card)
        return cards

    async def _process_shkvarkas(self):
        if self.pending_shkvarkas:
            for card in self.pending_shkvarkas:
                await self._handle_shkvarka(self.current_player_id, card)
        self.pending_shkvarkas = []

    async def _handle_add_ingredient(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Handle adding an ingredient to the player's borsht."""
        if 'card_id' not in move_data:
            return False, "Card ID required to add ingredient"

        card_uid = move_data['card_id']

        # Find the card in player's hand
        card_index = None
        for i, card in enumerate(self.player_hands[player_id]):
            if card['uid'] == card_uid:
                card_index = i
                break

        if card_index is None:
            return False, "Card not in hand"

        card = self.player_hands[player_id][card_index]

        # Check if it's a special card - these can't be added to borsht
        if card['type'] == 'special':
            return False, "Special ingredients cannot be added to borsht"

        if card['type'] == 'extra' and not self.game_settings.extra_cards_allowed:
            return False, "Extra cards not allowed"

        # Check if card in player's recipe
        if card['type'] in ['regular', 'rare'] and card['id'] not in self.player_recipes[player_id]["ingredients"]:
            return False, "Card not in your recipe"

        # Check if player already has this ingredient type
        for borsht_card in self.player_borsht[player_id]:
            if borsht_card['id'] == card['id']:
                return False, "You already have this ingredient in your borsht"

        # Add the card to the player's borsht
        self.player_borsht[player_id].append(card)
        # Remove from hand
        self.player_hands[player_id].pop(card_index)

        message = {
            'type': WebSocketGameMessage.INGREDIENT_ADDED,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'card': card,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        return True, None

    async def _handle_draw_cards(self, player_id: int) -> Tuple[bool, Optional[str]]:
        """Handle drawing 2 cards from the deck."""
        # Draw up to 2 cards
        cards_to_draw = self.game_settings.cards_to_draw
        drawn_cards = await self._get_cards_from_deck(cards_to_draw)

        if len(drawn_cards) == 0:
            return False, "No cards available to draw"

        # Add cards to player's hand
        self.player_hands[player_id].extend(drawn_cards)

        message = {
            'type': WebSocketGameMessage.CARDS_DRAWN,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'count': len(drawn_cards)
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        return True, None

    async def _handle_hand_limit(self, player_id: int) -> Tuple[bool, list]:
        """
        Handle situation when player's hand exceeds the limit.
        Request player to select cards to discard.

        Args:
            player_id (int): ID of the player

        Returns:
            Tuple[bool, list]: Success flag and remaining hand after discards
        """
        current_hand = self.player_hands[player_id].copy()
        hand_size = len(current_hand)
        limit = self.game_settings.player_hand_limit

        # unlimited hand
        if limit is None:
            return True, current_hand

        # Check if hand exceeds limit
        if hand_size <= limit:
            return True, current_hand

        self.turn_state = GameState.WAITING_FOR_DISCARD
        await self.send_game_update(player_id)

        # Calculate how many cards need to be discarded
        cards_to_discard = hand_size - limit

        success, updated_hand, discarded_cards = await self._cards_selection_request(
            owner_id=player_id,
            cards=current_hand,
            select_count=cards_to_discard,
            request_type='discard_selection',
            reason='hand_limit'
        )

        # Add discarded cards to discard pile
        self.discard_pile.extend(discarded_cards)

        # Notify about discard
        message = {
            'type': WebSocketGameMessage.CARDS_FROM_HAND_DISCARDED,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'cards': discarded_cards,
        }
        await self.connection_manager.broadcast(self.room_id, message)
        self.game_messages.append(message)

        return success, updated_hand

    async def _cards_selection_request(self, owner_id, cards, select_count, reason, request_type, selector_id=None, timeout=None):
        """
        General method to handle card discard selection from a collection of cards.

        Args:
            owner_id (int): ID of the player who owns the cards
            cards (List[Dict]): List of cards to select from
            select_count (int): Number of cards to discard/select
            reason (str): Reason for discard ('hand_limit', 'market_limit', 'shkvarka_effect', etc.)
            request_type (str): request type
            selector_id (int, optional): ID of the player making the selection (defaults to owner_id)
            timeout (int, optional): Timeout for selection (defaults to general_player_select_timeout)

        Returns:
            Tuple[bool, List[Dict], List[Dict]]: (success, remaining_cards, discarded_cards)
        """
        if select_count <= 0 or len(cards) <= 0:
            return True, cards, []

        # If not enough cards to discard, discard all
        if len(cards) <= select_count:
            return True, [], cards.copy()

        # Default selector to owner if not specified
        selector_id = selector_id if selector_id is not None else owner_id
        # Default timeout to general setting
        timeout = timeout if timeout is not None else self.game_settings.general_player_select_timeout

        # Save previous turn state and set waiting state
        previous_state = self.turn_state
        self.turn_state = GameState.WAITING_FOR_SELECTION
        await self.send_game_update(selector_id)

        # Prepare request data
        request_data = {
            'cards': cards,
            'select_count': select_count,
            'owner_player': jsonable_encoder(serialize_player(self.players[owner_id])),
            'reason': reason,
        }

        response = await self._request_to_player(
            player_id=selector_id,
            request_type=request_type,
            request_data=request_data,
            timeout=timeout,
        )

        # Restore previous turn state
        self.turn_state = previous_state

        # Process the response
        if response.get('timed_out', False) or response.get('random_select', False):
            # Select random cards for discard
            discard_indices = random.sample(range(len(cards)), select_count)
            discard_indices.sort(reverse=True)  # Sort in reverse to avoid index shifting

            # Create copies for manipulation
            updated_cards = cards.copy()
            discarded_cards = []

            # Remove cards and add to discard list
            for idx in discard_indices:
                discarded_cards.append(updated_cards[idx])
                updated_cards.pop(idx)

            return True, updated_cards, discarded_cards
        else:
            # Process player's selected cards
            selected_card_ids = response.get('selected_cards', [])

            # Validate selection count
            if len(selected_card_ids) != select_count:
                # Invalid selection, fall back to random
                return await self._cards_selection_request(owner_id, cards, select_count, reason, request_type, selector_id, timeout)

            # Find and process each selected card
            updated_cards = cards.copy()
            discarded_cards = []

            for card_id in selected_card_ids:
                card_found = False
                for i, card in enumerate(updated_cards):
                    if card['uid'] == card_id:
                        discarded_cards.append(card)
                        updated_cards.pop(i)
                        card_found = True
                        break

                if not card_found:
                    # Card not found, invalid selection, fall back to random
                    return await self._cards_selection_request(owner_id, cards, select_count, reason, request_type, selector_id,
                                                             timeout)

            return True, updated_cards, discarded_cards

    async def _handle_shkvarka(self, player_id, card):
        # Broadcast that a shkvarka card was drawn
        message = {
            'type': 'shkvarka_drawn',
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'card': card,
            'show_popup': True,
        }
        await self.connection_manager.broadcast(self.room_id, message)
        message['show_popup'] = False
        self.game_messages.append(message)

        if card.get('subtype', '') == 'permanent':
            self.active_shkvarkas.append(card)

        handler = self.__getattribute__(f"_handle_shkvarka_{card['id']}")
        if not handler:
            print(f"Shkvarka {card['id']} has no handler")
            return
        temp = self.turn_state
        self.turn_state = GameState.WAITING_FOR_SELECTION
        await self.broadcast_game_update()
        await handler(card)
        self.turn_state = temp
        await self.broadcast_game_update()

    async def _handle_special_ingredient(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str], bool]:
        """Handle playing a special ingredient for its effect."""
        if 'card_id' not in move_data:
            return False, "Card ID required to play special ingredient", True

        card_uid = move_data['card_id']

        # Find the card in player's hand
        card_index = None
        for i, card in enumerate(self.player_hands[player_id]):
            if card['uid'] == card_uid:
                card_index = i
                break

        if card_index is None:
            return False, "Card not in hand", True

        card = self.player_hands[player_id][card_index]

        # Check if it's a special card
        if card['type'] != 'special':
            return False, "Card is not a special ingredient", True

        # Process the special card effect
        effect = card['effect']
        success = False
        error_message = None
        is_move_continues = False

        # Handle different special card effects
        if effect == 'steal_or_discard':  # Chili Pepper
            success, error_message = await self._handle_chili_pepper(player_id, move_data)

        elif effect == 'discard_or_take':  # Black Pepper
            success, error_message = await self._handle_black_pepper(player_id, move_data)

        elif effect == 'defense':  # Sour Cream
            # This is handled passively when targeted by Chili or Black Pepper
            return False, "Sour Cream is used defensively when targeted by another player", True

        elif effect == 'take_market':  # Ginger
            success, error_message = await self._handle_ginger(player_id)

        elif effect == 'take_discard':  # Cinnamon
            success, error_message = await self._handle_cinnamon(player_id)

        elif effect == 'look_top_5':  # Olive Oil
            success, error_message = await self._handle_olive_oil(player_id)

        elif effect == 'refresh_market':  # Paprika
            success, error_message = await self._handle_paprika()
            is_move_continues = True

        if not success:
            return success, error_message, True

        self.player_hands[player_id].pop(card_index)
        self.discard_pile.append(card)

        message = {
            'type': WebSocketGameMessage.SPECIAL_PLAYED,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'special_card': card['id'],
            'effect': effect,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        await self.broadcast_game_update()

        return True, None, is_move_continues

    async def _handle_cinnamon(self, player_id):
        """
        Handle the Cinnamon special card effect.
        Allows player to choose up to n cards from the discard pile.
        """
        # Check if discard pile has any cards
        if len(self.discard_pile) == 0:
            return True, "No cards in discard pile"

        # Determine how many cards player can select (limited by discard pile size)
        max_select = min(self.game_settings.cinnamon_select_count, len(self.discard_pile))

        # Use the general discard request in "selection mode"
        success, remaining_discard, selected_cards = await self._cards_selection_request(
            owner_id=player_id,
            cards=self.discard_pile.copy(),
            select_count=max_select,
            request_type='cinnamon_selection',
            reason='cinnamon_selection'
        )

        # Update the discard pile
        self.discard_pile = remaining_discard

        # Add selected cards to player's hand
        self.player_hands[player_id].extend(selected_cards)

        # Notify about card selection
        message = {
            'type': WebSocketGameMessage.CARDS_FROM_DISCARD_SELECTED,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'cards': selected_cards,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        return True, None

    async def _handle_paprika(self):
        self.turn_state = GameState.WAITING_FOR_EXCHANGE
        await self._handle_market_refresh()
        return True, None

    async def _handle_olive_oil(self, player_id):
        look_count = self.game_settings.olive_oil_look_count
        select_count = self.game_settings.olive_oil_select_count

        if len(self.deck) < select_count:
            return False, "Not enough cards in deck"

        self.turn_state = GameState.WAITING_FOR_SELECTION
        await self.send_game_update(player_id)

        # Look at top n cards (or as many as available)
        top_cards = await self._get_cards_from_deck(look_count)

        # Use general discard request in "selection mode" (we keep the selected cards)
        success, cards_to_return, selected_cards = await self._cards_selection_request(
            owner_id=player_id,
            cards=top_cards,
            select_count=select_count,
            request_type='olive_oil_selection',
            reason='olive_oil_selection'
        )

        # Return unselected cards to the deck
        self.deck = cards_to_return + self.deck[look_count:]
        # Add selected cards to player's hand
        self.player_hands[player_id].extend(selected_cards)

        # Notify about selection
        await self.connection_manager.send(self.room_id, player_id, {
            'type': 'cards_selected',
            'cards': selected_cards,
        })

        return True, None

    async def _handle_ginger(self, player_id):
        """
        Handle the Ginger special card effect.
        Allows player to choose up to 3 cards from the market.

        Args:
            player_id (int): The ID of the player who played the Ginger card

        Returns:
            Tuple[bool, Optional[str]]: Success status and error message if any
        """
        # Check if market has any cards
        if len(self.market) == 0:
            return False, "No cards in market"

        self.turn_state = GameState.WAITING_FOR_SELECTION
        await self.send_game_update(player_id)
        # Determine how many cards player can select (limited by market size)
        max_select = min(self.game_settings.ginger_select_count, len(self.market))

        # Use the general discard request in "selection mode"
        success, remaining_market, selected_cards = await self._cards_selection_request(
            owner_id=player_id,
            cards=self.market.copy(),
            select_count=max_select,
            request_type='ginger_selection',
            reason='ginger_selection'
        )

        # Update the market
        self.market = remaining_market

        # Add selected cards to player's hand
        self.player_hands[player_id].extend(selected_cards)

        # Broadcast market update to all players
        message = {
            'type': WebSocketGameMessage.MARKET_CARDS_TAKEN,
            'market': selected_cards,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        # Refill the market
        await self._handle_market_refill()

        return True, None

    async def _handle_black_pepper(self, player_id, move_data):
        """
        Handle the Black Pepper special card effect.
        Allows player to either:
        - Take one random card from each opponent's hand
        - Force each opponent to discard one selected card from their borsht

        Args:
            player_id (int): The ID of the player who played the Black Pepper card
            move_data (Dict[str, Any]): Data containing card_id, action_type, and target_cards

        Returns:
            Tuple[bool, Optional[str]]: Success status and error message if any
        """
        # 1. Validate player has the card in hand
        card_uid = move_data.get('card_id')
        if not card_uid:
            return False, "Card ID required to play Black Pepper"

        card_index = None
        card = None
        for i, c in enumerate(self.player_hands[player_id]):
            if c['uid'] == card_uid:
                card_index = i
                card = c
                break

        if card_index is None:
            return False, "Card not in hand"

        if card['id'] != 'black_pepper':
            return False, "Selected card is not Black Pepper"

        # 2. Validate required parameters
        action_type = move_data.get('action_type')
        if not action_type:
            return False, "Action type required ('steal' or 'discard')"

        if action_type not in ['steal', 'discard']:
            return False, "Invalid action type. Must be 'steal' or 'discard'"

        # 3. Get valid target players (all opponents except first_finisher)
        valid_target_players = [pid for pid in self.players if pid != player_id and pid != self.first_finisher]

        if not valid_target_players:
            return False, "No valid targets available"

        # Broadcast the intended action
        message = {
            'type': WebSocketGameMessage.SPECIAL_EFFECT,
            'effect': 'black_pepper',
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'action_type': action_type
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        # Handle different action types
        if action_type == 'steal':
            # Take one random card from each opponent's hand
            return await self._handle_black_pepper_steal(player_id, valid_target_players, card)
        else:  # 'discard'
            # Force each opponent to discard one selected card from their borsht
            target_cards = move_data.get('target_cards', {})
            return await self._handle_black_pepper_discard(player_id, valid_target_players, target_cards, card)

    async def _handle_black_pepper_steal(self, player_id, target_players, card):
        """
        Handle Black Pepper's steal action - take one random card from each opponent's hand.

        Args:
            player_id (int): The acting player's ID
            target_players (List[int]): List of valid target player IDs
            card (Dict): The Black Pepper card object

        Returns:
            Tuple[bool, Optional[str]]: Success status and error message if any
        """
        # Track defense results for each player
        defense_results = {}
        stolen_cards = []

        # Check each target player for defense and process stealing
        for target_player in target_players:
            # Skip players with empty hands
            if len(self.player_hands[target_player]) == 0:
                continue

            # Check if target player has and wants to use a Sour Cream defense
            defense_used = await self._check_sour_cream_defense(target_player, card)
            defense_results[target_player] = defense_used

            # If no defense used, steal a random card
            if not defense_used:
                # Select a random card from target's hand
                import random
                random_index = random.randint(0, len(self.player_hands[target_player]) - 1)
                stolen_card = self.player_hands[target_player].pop(random_index)
                stolen_cards.append(stolen_card)

                # Add the stolen card to the current player's hand
                self.player_hands[player_id].append(stolen_card)

                # Notify that a card was stolen
                message = {
                    'type': WebSocketGameMessage.CARD_STOLEN,
                    'from_player': target_player,
                    'to_player': player_id
                }
                self.game_messages.append(message)
                await self.connection_manager.broadcast(self.room_id, message)

        # If no cards were stolen (all players defended or had empty hands)
        if not stolen_cards:
            return True, "No cards were stolen - all players defended or had empty hands"

        return True, None

    async def _handle_black_pepper_discard(self, player_id, target_players, target_cards, card):
        """
        Handle Black Pepper's discard action - force each opponent to discard a selected card from borsht.

        Args:
            player_id (int): The acting player's ID
            target_players (List[int]): List of valid target player IDs
            target_cards (Dict[str, str]): Mapping of player ID to card UIDs to discard
            card (Dict): The Black Pepper card object

        Returns:
            Tuple[bool, Optional[str]]: Success status and error message if any
        """
        # Validate target_cards includxes all valid targets
        if not target_cards:
            return False, "Target cards are required for discard action"

        # Validate all targets have a selected card to discard
        for target_player in target_players:
            # Skip players with empty borsht
            if len(self.player_borsht[target_player]) == 0:
                continue

            if str(target_player) not in target_cards:
                return False, f"Missing target card selection for player {target_player}"

            if target_cards[str(target_player)] not in [card['uid'] for card in self.player_borsht[target_player]]:
                return False, f"Card {target_cards[str(target_player)]} not found in player {target_player}'s borsht"

        # Track defense results for each player
        defense_results = {}
        discarded_cards = {}

        # Process each target
        for target_player in target_players:
            # Skip players with empty borsht
            if len(self.player_borsht[target_player]) == 0:
                continue

            target_card_uid = target_cards.get(str(target_player))
            if not target_card_uid:
                continue

            # Find the target card in the player's borsht
            target_card_index = None
            target_card = None

            for i, c in enumerate(self.player_borsht[target_player]):
                if c['uid'] == target_card_uid:
                    target_card_index = i
                    target_card = c
                    break

            # Check if target player has and wants to use a Sour Cream defense
            defense_used = await self._check_sour_cream_defense(target_player, card, [target_card])
            defense_results[target_player] = defense_used

            # If no defense used, discard the selected card
            if not defense_used:
                # Remove the card from target's borsht
                discarded_card = self.player_borsht[target_player].pop(target_card_index)
                discarded_cards[target_player] = discarded_card

                # Add to discard pile
                self.discard_pile.append(discarded_card)

                # Notify that a card was discarded
                message = {
                    'type': WebSocketGameMessage.BORSHT_CARD_DISCARDED,
                    'player': jsonable_encoder(serialize_player(self.players[target_player])),
                    'cards': [discarded_card],
                }
                self.game_messages.append(message)
                await self.connection_manager.broadcast(self.room_id, message)

        # If no cards were discarded (all players defended or had empty borsht)
        if not discarded_cards:
            return True, "No cards were discarded - all players defended or had empty borsht"

        return True, None

    async def _handle_chili_pepper(self, player_id, move_data):
        """
        Handle the Chili Pepper special card effect.
        Allows player to either steal or discard a card from target player's borsht.

        Args:
            player_id (int): The ID of the player who played the Chili Pepper card
            move_data (Dict[str, Any]): Data containing card_id, target_player, target_cards, and action_type

        Returns:
            Tuple[bool, Optional[str]]: Success status and error message if any
        """
        # 1. Validate player has the card in hand
        pepper_card_uid = move_data.get('card_id')
        if not pepper_card_uid:
            return False, "Card ID required to play Chili Pepper"

        pepper_card_index = None
        pepper_card = None
        for i, c in enumerate(self.player_hands[player_id]):
            if c['uid'] == pepper_card_uid:
                pepper_card_index = i
                pepper_card = c
                break

        if pepper_card_index is None:
            return False, "Card not in hand"

        if pepper_card['id'] != 'chili_pepper':
            return False, "Selected card is not Chili Pepper"

        # Validate required parameters
        target_player = int(move_data.get('target_player'))
        target_cards = move_data.get('target_cards', [])
        action_type = move_data.get('action_type')  # 'steal' or 'discard'

        if not target_player or not target_cards or not action_type:
            return False, "Target player, target cards, and action type required"

        if action_type not in ['steal', 'discard']:
            return False, "Invalid action type. Must be 'steal' or 'discard'"

        # Validate target player
        if target_player not in self.players or target_player == self.first_finisher:
            return False, "Invalid target player"

        # Validate target cards
        select_count = min(
            self.game_settings.chili_pepper_discard_count,
            len(self.player_borsht[target_player]),
        )
        if len(target_cards) != select_count:
            return False, f"Should be targeting at {select_count} cards"

        # 2. Validate all target cards exist in target player's borsht
        target_card_objects = []
        for card in target_cards:
            found = False
            for i, c in enumerate(self.player_borsht[target_player]):
                if c['uid'] == card['uid']:
                    target_card_objects.append((i, c))
                    found = True
                    break

            if not found:
                return False, f"Card {card['uid']} not found in target player's borsht"

        # Broadcast the intended action
        message = {
            'type': WebSocketGameMessage.SPECIAL_EFFECT,
            'effect': 'chili_pepper',
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'target_player': target_player,
            'target_cards': target_cards,
            'action_type': action_type
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        # 3. Check if target player has and wants to use a Sour Cream defense
        defense_used = await self._check_sour_cream_defense(target_player, pepper_card, [c for _, c in target_card_objects])

        # 4. Process the effect if no defense used
        if defense_used:
            return True, "Target defended with Sour Cream"

        # Process the effect based on action type
        # Sort indices in reverse to avoid shifting issues when removing
        target_card_objects.sort(key=lambda x: x[0], reverse=True)

        for idx, target_card in target_card_objects:
            # Remove the card from target player's borsht
            self.player_borsht[target_player].pop(idx)

            if action_type == 'steal':
                # Check if player already has this card in their borsht
                already_has = any(c['id'] == target_card['id'] for c in self.player_borsht[player_id])

                if already_has:
                    # Can't have duplicates in borsht, discard instead
                    self.discard_pile.append(target_card)
                else:
                    # Add to current player's borsht
                    self.player_borsht[player_id].append(target_card)
            else:  # 'discard'
                # Add to discard pile
                self.discard_pile.append(target_card)

        # 5. Broadcast the result
        message = {
            'type': WebSocketGameMessage.CHILI_PEPPER_EFFECT_APPLIED,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'target_player': target_player,
            'target_cards': target_cards,
            'action_type': action_type
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        return True, None

    async def _request_to_player(self, player_id: int, request_type: str,
                                 request_data: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        """
        Send a request to a player and wait for their response.

        Args:
            player_id (int): ID of the player to request from
            request_type (str): Type of request (e.g., 'defense_request', 'card_selection')
            request_data (Dict): Additional data for the request
            timeout (int): Seconds to wait for response before timing out

        Returns:
            Dict[str, Any]: Player's response or default response on timeout
        """
        # Create a unique request ID
        request_id = f"{request_type}_user{player_id}_{time.time()}_{random.randint(1000, 9999)}"
        expires_at = time.time() + timeout

        # Prepare the message
        request_message = {
            'type': request_type,
            'request_id': request_id,
            'expires_at': str(int(expires_at)),
            **request_data  # Include all additional data
        }

        try:
            # Send the request to the player
            await self.connection_manager.send(self.room_id, player_id, request_message)

            if player_id not in self.pending_requests:
                self.pending_requests[player_id] = {}

            # Create a future to wait for the response
            response_future = asyncio.Future()

            # Store the future somewhere accessible to the websocket handler
            self.pending_requests[player_id][request_id] = response_future
            self.sent_requests[request_id] = request_message

            # Wait for response with timeout
            try:
                # This will wait until the future is resolved or timeout occurs
                response = await asyncio.wait_for(response_future, timeout)
                return response
            except asyncio.TimeoutError:
                # Handle timeout - return default response
                return {'timed_out': True, 'request_id': request_id}
            finally:
                # Clean up the future regardless of outcome
                if request_id in self.pending_requests[player_id]:
                    del self.pending_requests[player_id][request_id]
                    del self.sent_requests[request_id]

        except Exception as e:
            # Log any errors that occur
            print(f"Error in player request: {e}")
            # Return error response
            return {'error': str(e), 'request_id': request_id}

    async def _check_sour_cream_defense(self, target_player: int, card: dict, target_cards=None) -> bool:
        """
        Check if target player has and wants to use a Sour Cream defense card.
        """
        # Check if player has Sour Cream in their hand
        sour_cream_indexes = []

        for i, player_card in enumerate(self.player_hands[target_player]):
            if (
                    player_card['id'] == 'sour_cream'
                    and player_card['type'] == 'special'
                    and player_card['effect'] == 'defense'
            ):
                sour_cream_indexes.append(i)
                if len(sour_cream_indexes) >= self.game_settings.smetana_count_for_defence:
                    break

        if len(sour_cream_indexes) < self.game_settings.smetana_count_for_defence:
            return False  # Player doesn't have enough defense cards

        temp = self.turn_state
        self.turn_state = GameState.WAITING_FOR_DEFENSE
        await self.send_game_update(self.current_player_id)
        # Prepare data for defense request
        request_data = {
            'attacker': self.current_player_id,
            'card': card,
            'target_cards': target_cards,
            'defense_cards': [self.player_hands[target_player][idx] for idx in sour_cream_indexes],
        }

        # Send defense request to player
        response = await self._request_to_player(
            player_id=target_player,
            request_type='defense_request',
            request_data=request_data,
            timeout=self.game_settings.general_player_select_timeout,
        )

        self.turn_state = temp

        # Check if player chose to use defense
        defense_used = response.get('use_defense', False) and not response.get('timed_out', False)

        if defense_used:
            # Remove Sour Cream from player's hand and put it in discard pile
            sour_cream_indexes.sort(reverse=True)
            for idx in sour_cream_indexes:
                defense_card = self.player_hands[target_player].pop(idx)
                self.discard_pile.append(defense_card)

            # Notify all players about the defense
            message = {
                'type': WebSocketGameMessage.DEFENSE_SUCCESSFUL,
                'defender': target_player,
                'attacker': self.current_player_id,
                'card': card,
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

        return defense_used

    async def _handle_market_limit(self) -> None:
        if len(self.market) < self.game_settings.market_capacity:
            await self._handle_market_refill()
        if len(self.market) > self.game_settings.market_capacity:
            # Calculate how many cards need to be discarded
            cards_to_discard = len(self.market) - self.game_settings.market_capacity

            temp_state = self.turn_state
            self.turn_state = GameState.WAITING_FOR_SELECTION
            await self.send_game_update(self.current_player_id)

            success, updated_market, discarded_cards = await self._cards_selection_request(
                owner_id=self.current_player_id,
                cards=self.market.copy(),
                select_count=cards_to_discard,
                request_type='discard_selection',
                reason='market_limit',
            )

            # Add discarded cards to discard pile
            self.discard_pile.extend(discarded_cards)
            self.market = updated_market
            self.turn_state = temp_state

            # Notify about discard
            message = {
                'type': WebSocketGameMessage.CARDS_FROM_MARKET_DISCARDED,
                'cards': [card['id'] for card in discarded_cards]
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

    async def _handle_market_refresh(self, cards_to_discard=None) -> None:
        """
        Discard all current market cards and replace them with new cards from the deck.
        """
        # Move selected or all current market cards to discard pile
        cards = cards_to_discard or self.market.copy()

        for card in cards:
            self.market.remove(card)
        self.discard_pile.extend(cards)

        message = {
            'type': WebSocketGameMessage.CARDS_FROM_MARKET_DISCARDED,
            'cards': cards,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        await self._handle_market_refill()

    async def _handle_market_refill(self) -> None:
        cards_to_add = self.game_settings.market_capacity - len(self.market)

        # Get new cards from deck
        new_cards = await self._get_cards_from_deck(cards_to_add)
        self.market.extend(new_cards)

        message = {
            'type': WebSocketGameMessage.MARKET_CARDS_ADDED,
            'cards': new_cards,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

    async def _handle_put_cards_to_market(self, cards):
        self.market.extend(cards)

        if len(self.market) > self.game_settings.market_capacity:
            cards_to_discard = self.game_settings.market_capacity - len(self.market)
            cards = self.market[cards_to_discard:]
            await self._handle_market_refresh(cards)

    async def _reshuffle_discard(self) -> None:
        """
        Reshuffle discard pile into the ingredient deck.
        """
        random.shuffle(self.discard_pile)
        self.deck.extend(self.discard_pile)
        self.discard_pile = []

        await self.broadcast_game_update()

    async def _handle_exchange(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Handle exchanging ingredients with the market."""
        if 'hand_cards' not in move_data or 'market_cards' not in move_data:
            return False, "Hand cards and market cards required for exchange"

        hand_cards = move_data['hand_cards']  # List of card IDs from hand
        market_cards = move_data['market_cards']  # List of card IDs from market

        # Verify exchange direction (1 to many or many to 1)
        if len(hand_cards) != 1 and len(market_cards) != 1:
            return False, "Exchange must be 1-to-many or many-to-1"

        # Calculate total cost of cards being exchanged
        hand_total_cost = 0
        hand_card_objects = []

        for card_uid in hand_cards:
            card_found = False
            for i, card in enumerate(self.player_hands[player_id]):
                if card['uid'] == card_uid:
                    hand_total_cost += card['cost']
                    hand_card_objects.append((i, card))
                    card_found = True
                    break
            if not card_found:
                return False, f"Card {card_uid} not in hand"

        market_total_cost = 0
        market_card_objects = []

        for card_uid in market_cards:
            card_found = False
            for i, card in enumerate(self.market):
                if card['uid'] == card_uid:
                    market_total_cost += card['cost']
                    market_card_objects.append((i, card))
                    card_found = True
                    break
            if not card_found:
                return False, f"Card {card_uid} not in market"

        price = market_total_cost + self.game_settings.market_exchange_tax
        if hand_total_cost < price:
            if not self.game_settings.market_exchange_tax:
                message = f"Hand card value ({hand_total_cost}) must be >= market cards total ({price})"
            else:
                message = f"Hand card value ({hand_total_cost}) must be >= market cards total plus {self.game_settings.market_exchange_tax} (sum {price})"

            return False, message

        # Exchange is valid, perform it
        # Remove cards from player's hand
        # Since we're removing items, we need to go in reverse index order to avoid shifting issues
        for i, _ in sorted(hand_card_objects, key=lambda x: x[0], reverse=True):
            self.player_hands[player_id].pop(i)

        # Remove cards from market
        # Same as above, remove in reverse index order
        for i, _ in sorted(market_card_objects, key=lambda x: x[0], reverse=True):
            self.market.pop(i)

        # Add market cards to player's hand
        self.player_hands[player_id].extend([card for _, card in market_card_objects])

        # Add player cards to market
        self.market.extend([card for _, card in hand_card_objects])

        message = {
            'type': WebSocketGameMessage.INGREDIENTS_EXCHANGED,
            'player': jsonable_encoder(serialize_player(self.players[player_id])),
            'hand_cards': hand_card_objects,
            'market_cards': market_card_objects,
        }
        self.game_messages.append(message)
        await self.connection_manager.broadcast(self.room_id, message)

        await self._handle_market_limit()

        return True, None

    def _check_recipe_completion(self, player_id) -> bool:
        """
        Check if player completed his recipe

        Returns:
            bool
        """
        recipe = self.player_recipes[player_id]
        recipe_ingredients = recipe['ingredients']

        player_borsht = self.player_borsht[player_id]

        player_borsht = [card for card in player_borsht if card['type'] in ['regular', 'rare'] or card['id'] == 'vinnik_lard']

        return len(player_borsht) >= len(recipe_ingredients)

    def check_game_over(self) -> Tuple[bool, Optional[int]]:
        """
        Check if any player has completed their borsch. If so, everyone else gets one more turn,
        then game ends. Calculate final scores.

        Returns:
            Tuple of (is_game_over, winner_id or None if no winner yet)
        """
        # If game is already marked as over, calculate winner
        if self.is_game_over:
            winner_id = self._determine_winner()
            return True, winner_id

        # Check if someone has completed their recipe
        if self.first_finisher is not None:
            # Check if we've gone around to the first finisher
            if self.current_player_id == self.first_finisher:
                # Everyone has had their final turn, game is over
                self.is_game_over = True
                winner_id = self._determine_winner()
                return True, winner_id
            # Game is ending but not over yet (other players get their final turn)
            return False, None

        # Check if any player has completed their recipe
        for player_id in self.players:
            if self._check_recipe_completion(player_id):
                # First player to complete recipe
                self.first_finisher = player_id
                self.game_ending = True
                # Other players get one more turn
                return False, None

        # No one has completed their recipe yet
        return False, None

    def _determine_winner(self) -> int:
        """Calculate scores and determine the winner."""
        scores = {}

        for player_id in self.players:
            # Base score from ingredients in borsht
            base_score = sum(card['points'] for card in self.player_borsht[player_id])

            # Calculate recipe completion score
            recipe = self.player_recipes[player_id]
            recipe_ingredients = recipe['ingredients']

            # Count how many required ingredients the player has
            player_ingredients = [card['id'] for card in self.player_borsht[player_id]]
            completed_ingredients = [ing for ing in recipe_ingredients if ing in player_ingredients or ing == "vinnik_lard"]
            completion_count = len(completed_ingredients)

            # Get recipe bonus points based on completion level
            recipe_bonus = 0
            for level, points in sorted(recipe['levels'].items()):
                if completion_count >= level:
                    recipe_bonus = points

            # Add bonus for being first to complete
            first_bonus = 2 if player_id == self.first_finisher else 0

            # Calculate final score
            final_score = base_score + recipe_bonus + first_bonus
            scores[player_id] = final_score

        # Find player with highest score
        max_score = -1
        winner_id = None

        for player_id, score in scores.items():
            if score > max_score:
                max_score = score
                winner_id = player_id
            elif score == max_score:
                # Compare sums of card values
                if sum(c['cost'] for c in self.player_hands[player_id]) > sum(c['cost'] for c in self.player_hands[winner_id]):
                    winner_id = player_id
                # In case of tie, the player who completed their recipe first wins
                elif player_id == self.first_finisher:
                    winner_id = player_id
                # If neither player completed recipe, the one with fewer moves wins
                elif self.first_finisher not in (player_id, winner_id):
                    if self.moves_count[player_id] < self.moves_count[winner_id]:
                        winner_id = player_id

        # Save winner info
        self.winner = winner_id
        return winner_id

    def calculate_scores(self) -> Dict[int, int]:
        """
        Calculate final scores for all players based on:
        - Points for each ingredient in borsch
        - Points for completed recipe levels

        Returns:
            Dictionary mapping player IDs to their final scores
        """
        scores = {}

        for player_id in self.players:
            # Calculate base points from ingredients
            ingredient_points = sum(card['points'] for card in self.player_borsht[player_id])

            # Get player's recipe
            recipe = self.player_recipes[player_id]
            recipe_ingredients = recipe['ingredients']

            # Count how many required ingredients the player has collected
            player_ingredients = [card['id'] for card in self.player_borsht[player_id]]
            completed_ingredients = [ing for ing in recipe_ingredients if ing in player_ingredients or ing  == 'vinnik_lard']
            completion_count = len(completed_ingredients)

            # Calculate recipe bonus based on completion levels
            recipe_bonus = 0
            for level, points in sorted(recipe['levels'].items()):
                if completion_count >= level:
                    recipe_bonus = points
                else:
                    break

            # Add first-completion bonus if applicable
            first_bonus = 2 if player_id == self.first_finisher else 0

            # Calculate final score
            final_score = ingredient_points + recipe_bonus + first_bonus

            scores[player_id] = final_score

        return scores

    def _is_market_free_refresh_available(self):
        card_counts = {}
        for card in self.market:
            card_id = card['id']
            card_counts[card_id] = card_counts.get(card_id, 0) + 1

            # If any card appears 3 or more times, return True immediately
            if card_counts[card_id] >= 3:
                return True

        # No set of 3+ identical cards found
        return False

    async def resend_pending_requests(self, user_id: int) -> None:
        for request in self.pending_requests.get(user_id, dict()):
            await self.connection_manager.send(self.room_id, user_id, self.sent_requests[request])

    async def resend_game_messages(self, user_id: int) -> None:
        for message in self.game_messages:
            await self.connection_manager.send(self.room_id, user_id, message)

    def get_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get current game state for sending to player.

        Returns sanitized game state with:
        - player's visible information
        - Market cards
        - Discard pile (top card)
        - Current player
        - Game phase information

        Args:
            player_id (int): ID of the player requesting the state

        Returns:
            Dict[str, Any]: Sanitized game state
        """
        if not self.is_started:
            return None

        state = dict(
            # Basic game state information
            current_player=self.current_player_id,
            is_game_over=self.is_game_over,
            game_ending=self.game_ending,
            first_finisher=jsonable_encoder(serialize_player(self.players[self.first_finisher])) if self.first_finisher else None,
            market_limit=self.game_settings.market_capacity,
            recipes_revealed=self.recipes_revealed,
            cards_in_deck=len(self.deck),
            turn_state=self.turn_state if player_id == self.current_player_id else None,

            # Market information
            market=self.market.copy(),
            free_refresh=self._is_market_free_refresh_available(),
            market_exchange_fee=self.game_settings.market_exchange_tax,

            # Discard pile - only show top card
            discard_pile_size=len(self.discard_pile),
            discard_pile_top=self.discard_pile[-1] if self.discard_pile else None,

            # Player-specific information
            your_hand=self.player_hands[player_id].copy(),
            your_borsht=self.player_borsht[player_id].copy(),
            your_recipe=self.player_recipes[player_id].copy(),

            # game settings
            hand_cards_limit=self.game_settings.player_hand_limit,
            market_base_limit=self.game_settings.market_base_capacity,
            chili_pepper_discard_count=self.game_settings.chili_pepper_discard_count,
            extra_cards_not_allowed=not self.game_settings.extra_cards_allowed,

            # Information about other players
            players=dict(),
        )

        for pid, player in self.players.items():
            # Skip the current player as their info is already included
            if pid == player_id:
                continue

            # For other players, only show public information
            state["players"][pid] = {
                "username": player.user.username,
                "hand_size": len(self.player_hands[pid]),
                "borsht": self.player_borsht[pid].copy(),  # Borsht ingredients are public information
            }

            # Recipe is only visible if recipes are revealed
            if self.recipes_revealed:
                state["players"][pid]["recipe"] = self.player_recipes[pid].copy()

        # Include active effects
        state["active_shkvarkas"] = self.active_shkvarkas.copy()

        return state

    def get_game_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the completed game.

        Returns:
            Dict[str, Any]: Dictionary with game stats including duration, winner,
                          points per player, ingredient usage, etc.
        """
        if not self.is_game_over:
            return {"error": "Game is not yet complete"}

        # Calculate game duration
        game_duration = time.time() - self.start_time

        # Get scores and determine winner
        scores = self.calculate_scores()
        winner_id = self.winner

        # Calculate additional stats
        player_stats = {}
        for player_id in self.players:
            # Get player's recipe and ingredients
            recipe = self.player_recipes[player_id]
            borsht_ingredients = self.player_borsht[player_id]

            # Count ingredient types in player's borsht
            ingredient_types = {
                "regular": 0,
                "rare": 0,
                "extra": 0,
                "special": 0
            }

            for card in borsht_ingredients:
                if card['type'] in ingredient_types:
                    ingredient_types[card['type']] += 1

            # Calculate recipe completion percentage
            recipe_ingredients = recipe['ingredients']
            player_ingredient_ids = [card['id'] for card in borsht_ingredients]
            completed_ingredients = [ing for ing in player_ingredient_ids if ing in recipe_ingredients or ing == 'vinnik_lard']
            completion_percentage = (len(completed_ingredients) / len(recipe_ingredients)) * 100

            # Calculate points breakdown
            ingredient_points = sum(card['points'] for card in borsht_ingredients)

            # Calculate recipe bonus
            recipe_bonus = 0
            for level, points in sorted(recipe['levels'].items()):
                if len(completed_ingredients) >= level:
                    recipe_bonus = points

            # First finisher bonus
            first_bonus = 2 if player_id == self.first_finisher else 0

            # Compile player statistics
            player_stats[player_id] = {
                "player": jsonable_encoder(serialize_player(self.players[player_id])),
                "recipe_name": recipe['name'],
                "recipe_completion": completion_percentage,
                "completed_ingredients": len(completed_ingredients),
                "total_recipe_ingredients": len(recipe_ingredients),
                "ingredient_types": ingredient_types,
                "total_ingredients": len(borsht_ingredients),
                "points_breakdown": {
                    "ingredient_points": ingredient_points,
                    "recipe_bonus": recipe_bonus,
                    "first_finisher_bonus": first_bonus,
                    "total_score": scores[player_id]
                },
                "moves_made": self.moves_count[player_id],
                "final_hand_size": len(self.player_hands[player_id])
            }

        # Game-wide statistics
        game_stats = {
            "duration_seconds": game_duration,
            "total_rounds": sum(self.moves_count.values()),
            "winner": jsonable_encoder(serialize_player(self.players[self.winner])),
            "winner_score": scores[winner_id],
            "scores": scores,
            "player_stats": player_stats,
            "first_finisher": jsonable_encoder(serialize_player(self.players[self.first_finisher])),
            "cards_remaining_in_deck": len(self.deck),
            "cards_in_discard": len(self.discard_pile),
            "active_shkvarkas": len(self.active_shkvarkas),
            "player_count": len(self.players)
        }

        return game_stats

    async def _handle_shkvarka_blackout(self, card):
        # TODO
        pass

    async def _handle_shkvarka_u_komori_myshi(self, card):
        """
        Handle the 'U Komori Myshi' shkvarka effect.
        Effect: Each player discards 2 arbitrary ingredients from the hand of the player to their left.
        """
        # Get ordered list of players for left-neighbor relationship
        player_ids = list(self.players.keys())

        # For each player, identify left neighbor and request discard
        requests = []
        for i, current_player in enumerate(player_ids):
            # Find left neighbor (clockwise direction)
            left_neighbor_idx = (i + 1) % len(player_ids)
            left_neighbor = player_ids[left_neighbor_idx]

            request = self._cards_selection_request(
                owner_id=left_neighbor,
                cards=self.player_hands[left_neighbor],
                select_count=2,
                reason='u_komori_myshi',
                request_type='shkvarka_effect_selection',
                selector_id=current_player,
            )
            task = asyncio.create_task(request)
            requests.append((current_player, left_neighbor, task))

        for current_player, left_neighbor, task in requests:
            if not task.done():
                await task
            success, updated_hand, discarded_cards = task.result()

            # Update the hand
            self.player_hands[left_neighbor] = updated_hand

            # Add discarded cards to discard pile
            self.discard_pile.extend(discarded_cards)

            # Notify players about the discard
            message = {
                'type': 'shkvarka_effect_discard',
                'card': card,
                'selector_player': jsonable_encoder(serialize_player(self.players[current_player])),
                'target_player': jsonable_encoder(serialize_player(self.players[left_neighbor])),
                'discarded_cards': discarded_cards
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

    async def _handle_shkvarka_garmyder_na_kuhni(self, card):
        """
        Handle the 'Garmyder na Kuhni' shkvarka effect.
        Effect: Each player passes their recipe card to the player on their left
        and now cooks a new borsht. Ingredients not in the new recipe are discarded.
        """
        # Get ordered list of players for left-neighbor relationship
        player_ids = list(self.players.keys())

        # Save current recipes
        old_recipes = {player_id: self.player_recipes[player_id] for player_id in player_ids}

        # Pass recipes to the left
        for i, current_player in enumerate(player_ids):
            # Find left neighbor (clockwise direction)
            left_neighbor_idx = (i + 1) % len(player_ids)
            left_neighbor = player_ids[left_neighbor_idx]

            # Pass recipe
            self.player_recipes[current_player] = old_recipes[left_neighbor]

        # For each player, discard ingredients not in new recipe
        for player_id in player_ids:
            new_recipe = self.player_recipes[player_id]
            required_ingredients = new_recipe["ingredients"]

            # Identify ingredients to discard
            discarded_ingredients = []
            updated_borsht = []

            for ingredient in self.player_borsht[player_id]:
                if ingredient['id'] in required_ingredients or ingredient['type'] == 'extra':
                    updated_borsht.append(ingredient)
                else:
                    discarded_ingredients.append(ingredient)

            # Update player's borsht
            self.player_borsht[player_id] = updated_borsht

            # Add discarded ingredients to discard pile
            self.discard_pile.extend(discarded_ingredients)

            # Notify about recipe change and discards
            message = {
                'type': WebSocketGameMessage.BORSHT_CARD_DISCARDED,
                'player': jsonable_encoder(serialize_player(self.players[player_id])),
                'cards': discarded_ingredients,
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

    async def _handle_shkvarka_zazdrisni_susidy(self, card):
        """
        Handle the 'Zazdrisni Susidy' shkvarka effect.
        Effect: The player with the most victory points discards any rare ingredient from their borsht.
        """
        # Calculate current points for each player
        player_points = {}
        for player_id in self.players:
            points = sum(card['points'] for card in self.player_borsht[player_id])
            player_points[player_id] = points

        # Find player with most points
        max_points = -1
        max_points_player = None

        for player_id, points in player_points.items():  # TODO: few players with most points
            if points > max_points:
                max_points = points
                max_points_player = player_id

        if not max_points_player:
            return  # No player has any points

        # Find all rare ingredients in the player's borsht
        rare_ingredients = [
            (i, ingredient) for i, ingredient in enumerate(self.player_borsht[max_points_player])
            if ingredient['type'] == 'rare' and not ingredient.get('face_down', False)
        ]

        if not rare_ingredients:
            # No rare ingredients to discard
            message = {
                'type': 'shkvarka_effect_no_rare',
                'card': card,
                'player': jsonable_encoder(serialize_player(self.players[max_points_player]))
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)
            return

        # Prepare cards for selection
        rare_cards = [card for _, card in rare_ingredients]

        success, _, discarded_cards = await self._cards_selection_request(
            owner_id=max_points_player,
            cards=rare_cards,
            select_count=1,
            reason='zazdrisni_susidy',
            request_type='shkvarka_effect_selection',
        )

        if success and discarded_cards:
            # Remove the selected card from borsht
            discarded_card = discarded_cards[0]
            for i, ingredient in enumerate(self.player_borsht[max_points_player]):
                if ingredient['uid'] == discarded_card['uid']:
                    self.player_borsht[max_points_player].pop(i)
                    break

            # Add to discard pile
            self.discard_pile.append(discarded_card)

            # Notify about the discard
            message = {
                'type': 'borsht_card_discarded',
                'cards': [discarded_card],
                'player': jsonable_encoder(serialize_player(self.players[max_points_player])),
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

    async def _handle_shkvarka_kuhar_rozbazikav(self, card):
        self.recipes_revealed = True

    async def _handle_shkvarka_mityng_zahysnykiv(self, card):
        """
        Handle the 'Mityng Zahysnykiv' shkvarka effect.
        Effect: Each player discards pork or beef from their borsht.
        """
        async def _process_player(player_id):
            # Find pork or beef in the player's borsht
            meat_cards = []
            for ingredient in self.player_borsht[player_id]:
                # Skip face-down cards
                if ingredient.get('face_down', False):
                    continue

                # Check if card is pork or beef
                if ingredient['id'] in ['pork', 'beef']:
                    meat_cards.append(ingredient)

            if not meat_cards:
                return  # No meat to discard

            success, _, discarded_cards = await self._cards_selection_request(
                owner_id=player_id,
                cards=meat_cards,
                select_count=1,
                reason='mityng_zahysnykiv',
                request_type='shkvarka_effect_selection',
            )

            if success and discarded_cards:
                # Remove the selected card from borsht
                discarded_card = discarded_cards[0]
                for idx, ingredient in enumerate(self.player_borsht[player_id]):
                    if ingredient['uid'] == discarded_card['uid']:
                        self.player_borsht[player_id].pop(idx)
                        break

                # Add to discard pile
                self.discard_pile.append(discarded_card)

                # Notify about the discard
                message = {
                    'type': WebSocketGameMessage.BORSHT_CARD_DISCARDED,
                    'cards': [discarded_card],
                    'player': jsonable_encoder(serialize_player(self.players[player_id])),
                }
                self.game_messages.append(message)
                await self.connection_manager.broadcast(self.room_id, message)
                await self.broadcast_game_update()

        tasks = []
        # Process each player
        for player_id in self.players:
            tasks.append(asyncio.create_task(_process_player(player_id)))
        for task in tasks:
            if not task.done():
                await task

    async def _handle_shkvarka_yarmarok(self, card):
        """
        Handle the 'Yarmarok' shkvarka effect.
        Effect: Each player selects a card from their hand and passes it to the player on their left.
        """
        # Get ordered list of players
        player_ids = list(self.players.keys())

        # For each player, request to select a card to pass
        selected_cards = {}
        requests = []

        for player_id in player_ids:
            # Skip if player has no cards
            if not self.player_hands[player_id]:
                continue

            request = self._cards_selection_request(
                owner_id=player_id,
                cards=self.player_hands[player_id],
                select_count=1,
                reason='yarmarok',
                request_type='shkvarka_effect_selection',
            )
            task = asyncio.create_task(request)
            requests.append((player_id, task))

        # Wait for all selections
        for player_id, task in requests:
            if not task.done():
                await task
            success, updated_hand, selected_card = task.result()

            if success and selected_card:
                # Update the player's hand and store selected card
                self.player_hands[player_id] = updated_hand
                selected_cards[player_id] = selected_card[0]

        # Pass cards to the left
        for i, current_player in enumerate(player_ids):
            if current_player not in selected_cards:
                continue

            # Find left neighbor
            left_neighbor_idx = (i + 1) % len(player_ids)
            left_neighbor = player_ids[left_neighbor_idx]

            # Pass the card
            passed_card = selected_cards[current_player]
            self.player_hands[left_neighbor].append(passed_card)

    async def _handle_shkvarka_zlodyi_nevdaha(self, card):
        # TODO
        pass

    async def _handle_shkvarka_vtratyv_niuh(self, card):
        """
        Handle the 'Vtratyv Niuh' shkvarka effect.
        Effect: Each player discards any extra ingredient from the borsht of the player to their right.
        """
        # Get ordered list of players
        player_ids = list(self.players.keys())
        tasks = []

        async def _process_player(current_player, right_neighbor):
            # Find extra ingredients in right neighbor's borsht
            extra_ingredients = [
                (idx, ingredient) for idx, ingredient in enumerate(self.player_borsht[right_neighbor])
                if ingredient.get('type') == 'extra' and not ingredient.get('face_down', False)
            ]

            if not extra_ingredients:
                return  # No extra ingredients to discard

            # Request current player to select an extra ingredient to discard
            extra_cards = [card for _, card in extra_ingredients]
            success, _, discarded_cards = await self._cards_selection_request(
                owner_id=right_neighbor,
                cards=extra_cards,
                select_count=1,
                reason='vtratyv_niuh',
                request_type='shkvarka_effect_selection',
                selector_id=current_player,
            )

            if success and discarded_cards:
                # Remove the selected card from borsht
                discarded_card = discarded_cards[0]
                for idx, ingredient in enumerate(self.player_borsht[right_neighbor]):
                    if ingredient['uid'] == discarded_card['uid']:
                        self.player_borsht[right_neighbor].pop(idx)
                        break

                # Add to discard pile
                self.discard_pile.append(discarded_card)

                # Notify about the discard
                message = {
                    'type': WebSocketGameMessage.BORSHT_CARD_DISCARDED,
                    'cards': [discarded_card],
                    'player': jsonable_encoder(serialize_player(self.players[right_neighbor])),
                }
                self.game_messages.append(message)
                await self.connection_manager.broadcast(self.room_id, message)
                await self.broadcast_game_update()

        # For each player, identify right neighbor and process
        for i, current_player in enumerate(player_ids):
            # Find right neighbor (counter-clockwise)
            right_neighbor_idx = (i - 1) % len(player_ids)
            right_neighbor = player_ids[right_neighbor_idx]

            tasks.append(asyncio.create_task(_process_player(current_player, right_neighbor)))

        for task in tasks:
            if not task.done():
                await task

    async def _handle_shkvarka_den_vrozhaiu(self, card):
        """
        Handle the 'Den Vrozhaiu' shkvarka effect.
        Effect: Each player discards 1 ingredient from their borsht that is currently in the market.
        """
        # Get market ingredient IDs
        market_ingredient_ids = set(card['id'] for card in self.market)
        tasks = []

        async def _process_player(player_id):
            # Find ingredients in player's borsht that are in the market
            matching_ingredients = [
                (idx, ingredient) for idx, ingredient in enumerate(self.player_borsht[player_id])
                if ingredient['id'] in market_ingredient_ids and not ingredient.get('face_down', False)
            ]

            if not matching_ingredients:
                return  # No matching ingredients to discard

            # Request player to select an ingredient to discard
            matching_cards = [card for _, card in matching_ingredients]
            success, _, discarded_cards = await self._cards_selection_request(
                owner_id=player_id,
                cards=matching_cards,
                select_count=1,
                reason='den_vrozhaiu',
                request_type='shkvarka_effect_selection',
            )

            if success and discarded_cards:
                # Remove the selected card from borsht
                discarded_card = discarded_cards[0]
                for idx, ingredient in enumerate(self.player_borsht[player_id]):
                    if ingredient['uid'] == discarded_card['uid']:
                        self.player_borsht[player_id].pop(idx)
                        break

                # Add to discard pile
                self.discard_pile.append(discarded_card)

                # Notify about the discard
                message = {
                    'type': WebSocketGameMessage.BORSHT_CARD_DISCARDED,
                    'cards': [discarded_card],
                    'player': jsonable_encoder(serialize_player(self.players[player_id])),
                }
                self.game_messages.append(message)
                await self.connection_manager.broadcast(self.room_id, message)
                await self.broadcast_game_update()

        # Process each player
        for player_id in self.players:
            tasks.append(asyncio.create_task(_process_player(player_id)))

        for task in tasks:
            if not task.done():
                await task

    async def _handle_shkvarka_zgorila_zasmazhka(self, card):
        """
        Handle the 'Zgorila Zasmazhka' shkvarka effect.
        Effect: All players discard onions and carrots from their borshts.
        """
        # Process each player
        for player_id in self.players:
            # Find onions and carrots in player's borsht
            zasmazhka_indices = []

            for idx, ingredient in enumerate(self.player_borsht[player_id]):
                # Skip face-down cards
                if ingredient.get('face_down', False):
                    continue

                # Check if card is onion or carrot
                if ingredient['id'] in ['onion', 'carrot']:
                    zasmazhka_indices.append(idx)

            if not zasmazhka_indices:
                continue  # No onions or carrots to discard

            # Sort in reverse to avoid index shifting when removing
            zasmazhka_indices.sort(reverse=True)

            # Remove ingredients and track discarded cards
            discarded_cards = []
            for idx in zasmazhka_indices:
                discarded_cards.append(self.player_borsht[player_id][idx])
                self.player_borsht[player_id].pop(idx)

            # Add to discard pile
            self.discard_pile.extend(discarded_cards)

            # Notify about the discard
            message = {
                'type': WebSocketGameMessage.BORSHT_CARD_DISCARDED,
                'cards': discarded_cards,
                'player': jsonable_encoder(serialize_player(self.players[player_id])),
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

    async def _handle_shkvarka_zagubyly_spysok(self, card):
        """
        Handle the 'Zagubyly Spysok' shkvarka effect.
        Effect: Each player discards 1 ingredient from their borsht that is NOT currently in the market.
        """
        # Get market ingredient IDs
        market_ingredient_ids = set(card['id'] for card in self.market)

        async def _process_player(player_id):
            # Find ingredients in player's borsht that are NOT in the market
            matching_ingredients = [
                (idx, ingredient) for idx, ingredient in enumerate(self.player_borsht[player_id])
                if ingredient['id'] not in market_ingredient_ids and not ingredient.get('face_down', False)
            ]

            if not matching_ingredients:
                return  # No matching ingredients to discard

            # Request player to select an ingredient to discard
            matching_cards = [card for _, card in matching_ingredients]
            success, _, discarded_cards = await self._cards_selection_request(
                owner_id=player_id,
                cards=matching_cards,
                select_count=1,
                reason='zagubyly_spysok',
                request_type='shkvarka_effect_selection',
            )

            if success and discarded_cards:
                # Remove the selected card from borsht
                discarded_card = discarded_cards[0]
                for idx, ingredient in enumerate(self.player_borsht[player_id]):
                    if ingredient['uid'] == discarded_card['uid']:
                        self.player_borsht[player_id].pop(idx)
                        break

                # Add to discard pile
                self.discard_pile.append(discarded_card)

                # Notify about the discard
                message = {
                    'type': WebSocketGameMessage.BORSHT_CARD_DISCARDED,
                    'player': jsonable_encoder(serialize_player(self.players[player_id])),
                    'cards': [discarded_card],
                }
                self.game_messages.append(message)
                await self.connection_manager.broadcast(self.room_id, message)
                await self.broadcast_game_update()

        tasks = []
        # Process each player
        for player_id in self.players:
            tasks.append(asyncio.create_task(_process_player(player_id)))

        for task in tasks:
            if not task.done():
                await task

    async def _handle_shkvarka_rozsypaly_specii(self, card):
        """
        Handle the 'Rozsypaly Specii' shkvarka effect.
        Effect: Each player discards an ingredient from the borsht of the player to their left
        (target can defend with Sour Cream).
        """
        async def _process_player(current_player, left_neighbor, card):
            # Skip if left neighbor has no ingredients or is the first finisher
            if not self.player_borsht[left_neighbor] or left_neighbor == self.first_finisher:
                return

            # Find non-face-down ingredients in left neighbor's borsht
            valid_ingredients = [
                (idx, ingredient) for idx, ingredient in enumerate(self.player_borsht[left_neighbor])
                if not ingredient.get('face_down', False)
            ]

            if not valid_ingredients:
                return  # No valid ingredients to discard

            # Request current player to select an ingredient to discard
            valid_cards = [card for _, card in valid_ingredients]

            success, _, discarded_cards = await self._cards_selection_request(
                owner_id=left_neighbor,
                cards=valid_cards,
                select_count=1,
                reason='rozsypaly_specii',
                request_type='shkvarka_effect_selection',
                selector_id=current_player,
            )

            if success and discarded_cards:
                # Check if left neighbor can and wants to defend with Sour Cream
                defense_used = await self._check_sour_cream_defense(left_neighbor, card, discarded_cards)
                if defense_used:
                    return
                # Remove the selected card from borsht
                discarded_card = discarded_cards[0]
                for idx, ingredient in enumerate(self.player_borsht[left_neighbor]):
                    if ingredient['uid'] == discarded_card['uid']:
                        self.player_borsht[left_neighbor].pop(idx)
                        break

                # Add to discard pile
                self.discard_pile.append(discarded_card)

                # Notify about the discard
                message = {
                    'type': WebSocketGameMessage.BORSHT_CARD_DISCARDED,
                    'player': jsonable_encoder(serialize_player(self.players[left_neighbor])),
                    'cards': [discarded_card],
                }
                self.game_messages.append(message)
                await self.connection_manager.broadcast(self.room_id, message)
                await self.broadcast_game_update()

        # Get ordered list of players
        player_ids = list(self.players.keys())
        tasks = []

        # For each player, identify left neighbor and process
        for i, current_player in enumerate(player_ids):
            # Find left neighbor (clockwise)
            left_neighbor_idx = (i + 1) % len(player_ids)
            left_neighbor = player_ids[left_neighbor_idx]

            tasks.append(asyncio.create_task(_process_player(current_player, left_neighbor, card)))

        for task in tasks:
            if not task.done():
                await task

    async def _handle_shkvarka_postachalnyk_pereplutav(self, card):
        """
        Handle the 'Postachalnyk Pereplutav' shkvarka effect.
        Effect: Starting with the active player, each player in turn discards
        all cards from their hand and draws 5 new ones from the deck.
        """
        # Get ordered list of players starting with current player
        current_idx = -1

        # Find current player index
        for i, player_id in enumerate(self.players):
            if player_id == self.current_player_id:
                current_idx = i
                break

        if current_idx == -1:
            # Fallback if current player not found
            ordered_players = list(self.players.keys())
        else:
            # Create ordered list starting with current player
            player_ids = list(self.players.keys())
            ordered_players = player_ids[current_idx:] + player_ids[:current_idx]

        # Process each player in turn
        for player_id in ordered_players:
            # Discard all cards from hand
            discarded_cards = self.player_hands[player_id].copy()
            self.discard_pile.extend(discarded_cards)
            self.player_hands[player_id] = []

            # Draw 5 new cards (or as many as available)
            new_cards = await self._get_cards_from_deck(5)
            self.player_hands[player_id].extend(new_cards)

            # Notify about the discard and draw
            message = {
                'type': WebSocketGameMessage.CARDS_FROM_HAND_DISCARDED,
                'cards': discarded_cards,
                'player': jsonable_encoder(serialize_player(self.players[player_id])),
            }
            self.game_messages.append(message)
            await self.connection_manager.broadcast(self.room_id, message)

    async def _handle_shkvarka_defolt_crisa(self, card):
        self.game_settings.market_exchange_tax = 1

    async def _handle_shkvarka_sanepidemstancia(self, card):
        self.game_settings.market_capacity -= 2
        await self._handle_market_limit()

    async def _handle_shkvarka_kayenskyi_perec(self, card):
        self.game_settings.chili_pepper_discard_count = 2

    async def _handle_shkvarka_porvalas_torbynka(self, card):
        async def _process_player(player_id):
            limit_success, updated_hand = await self._handle_hand_limit(player_id)
            if limit_success:
                self.player_hands[player_id] = updated_hand
            await self.broadcast_game_update()

        self.game_settings.player_hand_limit = 4
        tasks = []
        for player_id in self.players:
            tasks.append(asyncio.create_task(_process_player(player_id)))

        for task in tasks:
            if not task.done():
                await task

    async def _handle_shkvarka_peresolyly(self, card):
        self.game_settings.extra_cards_allowed = False

    async def _handle_shkvarka_molochka_skysla(self, card):
        self.game_settings.smetana_count_for_defence = 2

    def dump(self) -> dict:
        """
        Serialize the game manager state to a dictionary for persistence.

        Returns:
            Dictionary containing the serialized game state
        """
        # First call the parent class dump method to get basic state
        base_state = super().dump()

        # Add Borsht-specific state
        borsht_state = {
            # Game settings
            'game_settings': {
                'cards_to_draw': self.game_settings.cards_to_draw,
                'borscht_recipes_select_count': self.game_settings.borscht_recipes_select_count,
                'disposable_shkvarka_count': self.game_settings.disposable_shkvarka_count,
                'permanent_shkvarka_count': self.game_settings.permanent_shkvarka_count,
                'market_capacity': self.game_settings.market_capacity,
                'market_base_capacity': self.game_settings.market_base_capacity,
                'player_hand_limit': self.game_settings.player_hand_limit,
                'player_start_hand_size': self.game_settings.player_start_hand_size,
                'market_exchange_tax': self.game_settings.market_exchange_tax,
                'extra_cards_allowed': self.game_settings.extra_cards_allowed,
                'olive_oil_look_count': self.game_settings.olive_oil_look_count,
                'olive_oil_select_count': self.game_settings.olive_oil_select_count,
                'cinnamon_select_count': self.game_settings.cinnamon_select_count,
                'ginger_select_count': self.game_settings.ginger_select_count,
                'chili_pepper_discard_count': self.game_settings.chili_pepper_discard_count,
                'smetana_count_for_defence': self.game_settings.smetana_count_for_defence,
            },

            # Game state
            'is_started': self.is_started,
            'start_time': self.start_time,
            'turn_state': self.turn_state,
            'market': self.market,
            'deck': self.deck,
            'discard_pile': self.discard_pile,
            'pending_shkvarkas': self.pending_shkvarkas,
            'recipes_revealed': self.recipes_revealed,
            'game_ending': self.game_ending,
            'first_finisher': self.first_finisher,
            'active_shkvarkas': self.active_shkvarkas,
            'recipes': self.recipes if hasattr(self, 'recipes') else [],

            # Player state
            'player_recipes': self.player_recipes,
            'player_borsht': self.player_borsht,
            'player_hands': self.player_hands,
            'moves_count': self.moves_count,
        }

        # Merge the base state with Borsht-specific state
        base_state.update(borsht_state)

        return base_state

    @classmethod
    def load(cls, db, room, connection_manager, saved_state: dict) -> 'BorshtManager':
        """
        Create a new Borsht game manager instance from a saved state.

        Args:
            db: Database connection
            room: Room object
            connection_manager: WebSocket connection manager
            saved_state: Dictionary containing the serialized game state

        Returns:
            New BorshtManager instance with restored state
        """
        # Extract game settings from saved state
        game_settings = saved_state.get('game_settings', {})

        # Create a new instance with the saved settings
        instance = cls(db, room, connection_manager, game_settings)

        # Set the flag indicating the game has already been started
        instance.is_started = saved_state.get('is_started', False)

        # Restore base state using parent class load method
        super(BorshtManager, cls).load(db, room, connection_manager, saved_state)

        # Restore Borsht-specific state
        instance.start_time = saved_state.get('start_time', time.time())
        instance.turn_state = saved_state.get('turn_state', GameState.NORMAL_TURN)
        instance.market = saved_state.get('market', [])
        instance.deck = saved_state.get('deck', [])
        instance.discard_pile = saved_state.get('discard_pile', [])
        instance.pending_shkvarkas = saved_state.get('pending_shkvarkas', [])
        instance.recipes_revealed = saved_state.get('recipes_revealed', False)
        instance.game_ending = saved_state.get('game_ending', False)
        instance.first_finisher = saved_state.get('first_finisher')
        instance.active_shkvarkas = saved_state.get('active_shkvarkas', [])

        # Restore player state
        temp = saved_state.get('player_recipes', {})
        for key in temp:
            instance.player_recipes[int(key)] = temp[key]
        temp = saved_state.get('player_borsht', {})
        for key in temp:
            instance.player_borsht[int(key)] = temp[key]
        temp = saved_state.get('player_hands', {})
        for key in temp:
            instance.player_hands[int(key)] = temp[key]
        temp = saved_state.get('moves_count', {})
        for key in temp:
            instance.moves_count[int(key)] = temp[key]

        # Restore recipes if available
        if 'recipes' in saved_state:
            instance.recipes = saved_state['recipes']

        # Ensure all player IDs are properly restored as integers
        for attr in ['player_recipes', 'player_borsht', 'player_hands', 'moves_count']:
            data = getattr(instance, attr, {})
            if isinstance(data, dict):
                # Convert string keys back to integers if needed
                converted_data = {}
                for k, v in data.items():
                    key = int(k) if isinstance(k, str) else k
                    converted_data[key] = v
                setattr(instance, attr, converted_data)

        return instance
