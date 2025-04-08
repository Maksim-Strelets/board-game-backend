# app/games/borsht/game_manager.py
import asyncio
from typing import Dict, Any, Tuple, List, Optional
import random
import time

from fastapi.encoders import jsonable_encoder

from app.games.abstract_game import AbstractGameManager
from app.serializers.game import serialize_players

from app.games.borsht import game_cards


class GameSettings:
    borscht_recipes_select_count = 3
    borscht_recipes_select_timeout = 30
    market_capacity = 8
    player_hand_limit = 8
    player_start_hand_size = 5
    market_exchange_tax = 0


class BorshtManager(AbstractGameManager):
    game_settings = GameSettings()

    """Implementation of Borsht card game logic."""

    def __init__(self, db, room, connection_manager):
        self.is_started = False

        super().__init__(db, room, connection_manager)
        # Ensure we have 2-5 players (based on game rules)
        if len(room.players) < 2 or len(room.players) > 5:
            raise ValueError("Borsht requires 2-5 players")

        # Track game start time for statistics
        self.start_time = time.time()

        # Player state tracking
        self.player_recipes = {}  # Will store the recipe card for each player
        self.player_borsht = {}  # Will store ingredients in each player's borsht
        self.player_hands = {}  # Will store cards in each player's hand
        self.moves_count = {player.user_id: 0 for player in room.players}

        # Game state
        self.market = []  # Cards available in the market
        self.deck = []  # Main ingredient deck
        self.discard_pile = []  # Discard pile

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
        self._setup_market()

        self.is_started = True
        for player in self.players:
            await self.connection_manager.send(self.room_id, player, {
                "type": "game_state",
                "state": jsonable_encoder(self.get_state(player)),
            })

    def _generate_deck(self):
        """Generate the ingredient deck based on game rules."""
        # This would typically come from a database, but for this example,
        # we'll define it directly in code based on the game rulebook
        self.deck = game_cards.base_cards.copy()  # TODO: check copying

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
                    timeout=self.game_settings.borscht_recipes_select_timeout
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

    def _setup_market(self):
        """Set up the initial market with 8 cards."""
        # Draw the top 8 cards from the deck for the market
        self.market = self.deck[:self.game_settings.market_capacity]
        self.deck = self.deck[self.game_settings.market_capacity:]

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

        # Track move count
        self.moves_count[player_id] += 1

        # Process different action types
        if action == 'add_ingredient':
            # Add an ingredient to the player's borsht
            success, error_message = await self._handle_add_ingredient(player_id, move_data)

        elif action == 'draw_cards':
            # Draw 2 cards from the deck
            success, error_message = await self._handle_draw_cards(player_id)

        elif action == 'play_special':
            # Play a special ingredient card for its effect
            success, error_message = await self._handle_special_ingredient(player_id, move_data)

        elif action == 'exchange_ingredients':
            # Exchange ingredients with the market
            success, error_message = await self._handle_exchange(player_id, move_data)

        elif action == 'free_market_refresh':
            # Refresh the market
            success, error_message = await self._handle_free_market_refresh()
            return success, error_message, self.is_game_over

        else:
            error_message = "Invalid action type"

        # Check if player has completed their recipe
        recipe_completed = self._check_recipe_completion(player_id)

        # If player completed recipe and it's the first to do so
        if recipe_completed and self.first_finisher is None:
            self.first_finisher = player_id
            self.game_ending = True
            await self.connection_manager.broadcast(self.room_id, {
                'type': 'recipe_completed',
                'player_id': player_id,
                'is_first': True
            })

        # Check if game is over (all players have had their final turn)
        if self.game_ending:
            # If we've gone around to the player who completed their recipe first
            if str(player_id) == str(self.first_finisher) and self.current_player_index == self.players.index(
                    player_id):
                self.is_game_over = True
                self._determine_winner()

        # If move was successful and game not over, advance to next player
        if success and not self.is_game_over:
            self.next_player()

        for player_id in self.players.keys():
            await self.connection_manager.send(self.room_id, player_id, {
                "type": "game_update",
                "state": jsonable_encoder(self.get_state(player_id))
            })

        return success, error_message, self.is_game_over

    async def _handle_free_market_refresh(self) -> tuple[bool, Optional[str]]:
        if not self._is_market_free_refresh_available():
            return False, "Free market refresh not available"

        await self._handle_market_refresh()

        return True, None

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

        await self.connection_manager.broadcast(self.room_id, {
            'type': 'ingredient_added',
            'player_id': player_id,
            'card': card,
        })

        return True, None

    async def _handle_draw_cards(self, player_id: int) -> Tuple[bool, Optional[str]]:
        """Handle drawing 2 cards from the deck."""
        # Check if there are enough cards in the deck
        if len(self.deck) < 2:
            # If not enough cards, shuffle the discard pile
            if len(self.discard_pile) > 0:
                import random
                self.deck.extend(self.discard_pile)
                random.shuffle(self.deck)
                self.discard_pile = []

            # If still not enough cards, draw what's available
            if len(self.deck) == 0:
                return False, "No cards available to draw"

        # Draw up to 2 cards
        cards_to_draw = min(2, len(self.deck))
        drawn_cards = self.deck[:cards_to_draw]
        self.deck = self.deck[cards_to_draw:]

        # Check for shkvarka cards and process them
        for i, card in enumerate(drawn_cards):
            if card.get('type') == 'shkvarka':
                # Process shkvarka card
                self._handle_shkvarka(player_id, card)
                # Replace shkvarka card with a new card from deck
                if len(self.deck) > 0:
                    drawn_cards[i] = self.deck.pop(0)
                else:
                    # If no more cards, just remove the shkvarka
                    drawn_cards.pop(i)

        # Add cards to player's hand
        self.player_hands[player_id].extend(drawn_cards)

        # Check hand limit and ask player to discard if needed
        success, updated_hand = await self._handle_hand_limit(player_id, self.player_hands[player_id])
        if success:
            self.player_hands[player_id] = updated_hand
        else:
            # This shouldn't happen, but just in case
            return False, "Failed to handle hand limit"

        await self.connection_manager.broadcast(self.room_id, {
            'type': 'cards_drawn',
            'player_id': player_id,
            'count': len(drawn_cards)
        })

        return True, None

    async def _handle_hand_limit(self, player_id: int, current_hand: list) -> Tuple[bool, list]:
        """
        Handle situation when player's hand exceeds the limit.
        Request player to select cards to discard.

        Args:
            player_id (int): ID of the player
            current_hand (list): Current hand of cards

        Returns:
            Tuple[bool, list]: Success flag and remaining hand after discards
        """
        hand_size = len(current_hand)
        limit = self.game_settings.player_hand_limit

        # Check if hand exceeds limit
        if hand_size <= limit:
            return True, current_hand

        # Calculate how many cards need to be discarded
        cards_to_discard = hand_size - limit

        # Prepare request data
        request_data = {
            'hand': current_hand,
            'discard_count': cards_to_discard,
            'reason': 'hand_limit',
            'your_recipe': self.player_recipes[player_id],
        }

        # Send discard selection request to player
        response = await self._request_to_player(
            player_id=player_id,
            request_type='discard_selection',
            request_data=request_data,
            timeout=30  # 30 second timeout
        )

        # Process the response
        if response.get('timed_out', False) or response.get('random_discard', False):
            # discard random cards
            discard_indices = random.sample(range(hand_size), cards_to_discard)
            discard_indices.sort(reverse=True)  # Sort in reverse to avoid index shifting

            # Create copies of the hand for manipulation
            updated_hand = current_hand.copy()
            discarded_cards = []

            # Remove cards from hand and add to discard pile
            for idx in discard_indices:
                discarded_cards.append(updated_hand[idx])
                updated_hand.pop(idx)

            # Add discarded cards to discard pile
            self.discard_pile.extend(discarded_cards)

            # Notify about random discard
            await self.connection_manager.send(self.room_id, player_id, {
                'type': 'cards_discarded',
                'player_id': player_id,
                'count': cards_to_discard
            })

            return True, updated_hand
        else:
            # Get player's selected cards to discard
            selected_card_ids = response.get('selected_cards', [])

            # Validate selection
            if len(selected_card_ids) != cards_to_discard:
                # Invalid selection, fall back to random
                return await self._handle_hand_limit(player_id, current_hand)

            # Find the cards in the hand
            updated_hand = current_hand.copy()
            discarded_cards = []

            # Process each selected card
            for card_id in selected_card_ids:
                card_found = False
                for i, card in enumerate(updated_hand):
                    if card['uid'] == card_id:
                        discarded_cards.append(card)
                        updated_hand.pop(i)
                        card_found = True
                        break

                if not card_found:
                    # Card not found, invalid selection
                    return await self._handle_hand_limit(player_id, current_hand)

            # Add discarded cards to discard pile
            self.discard_pile.extend(discarded_cards)

            # Notify about discard
            await self.connection_manager.send(self.room_id, player_id, {
                'type': 'cards_discarded',
                'player_id': player_id,
                'cards': [card['id'] for card in discarded_cards]
            })

            return True, updated_hand

    def _handle_shkvarka(self, player_id, card):
        pass

    async def _handle_special_ingredient(self, player_id: int, move_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Handle playing a special ingredient for its effect."""
        if 'card_id' not in move_data:
            return False, "Card ID required to play special ingredient"

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

        # Check if it's a special card
        if card['type'] != 'special':
            return False, "Card is not a special ingredient"

        # Process the special card effect
        effect = card['effect']
        success = False
        error_message = None

        # Handle different special card effects
        if effect == 'steal_or_discard':  # Chili Pepper
            if 'target_player' not in move_data or 'target_card' not in move_data or 'action_type' not in move_data:
                return False, "Target player, target card, and action type required for this effect"

            target_player = move_data['target_player']
            target_card = move_data['target_card']
            action_type = move_data['action_type']  # 'steal' or 'discard'

            await self.connection_manager.broadcast(self.room_id, {
                'type': 'special_effect',
                'effect': 'steal_or_discard',
                'player_id': player_id,
                'target_player': target_player,
                'target_card': target_card,
                'action_type': action_type
            })

            # Check if target player has a sour cream defense
            defense_used = await self._check_sour_cream_defense(target_player, card)
            if defense_used:
                # Remove the card from player's hand and add to discard pile
                self.player_hands[player_id].pop(card_index)
                self.discard_pile.append(card)
                return True, "Target defended with Sour Cream"

            # Find the target card in target player's borsht
            target_card_obj = None
            for i, c in enumerate(self.player_borsht[target_player]):
                if c['id'] == target_card:
                    target_card_obj = c
                    target_card_index = i
                    break

            if target_card_obj is None:
                return False, "Target card not found in target player's borsht"

            if action_type == 'steal': # TODO: check card already in borscht
                # Move card from target player's borsht to current player's borsht
                self.player_borsht[target_player].pop(target_card_index)
                self.player_borsht[player_id].append(target_card_obj)
            else:  # 'discard'
                # Remove card from target player's borsht
                self.player_borsht[target_player].pop(target_card_index)
                self.discard_pile.append(target_card_obj)

            success = True

        elif effect == 'discard_or_take':  # Black Pepper
            if 'effect_choice' not in move_data:
                return False, "Effect choice required for Black Pepper"

            effect_choice = move_data['effect_choice']  # 'discard_from_borsht' or 'take_from_hand'

            await self.connection_manager.broadcast(self.room_id, {
                'type': 'special_effect',
                'effect': 'discard_or_take',
                'player_id': player_id,
                'effect_choice': effect_choice,
                'affected_players': [p for p in self.players if p != player_id]
            })

            # Apply effect to all other players
            for target_player in self.players:
                if target_player == player_id:
                    continue  # Skip current player

                # Check if target player has a sour cream defense
                defense_used = await self._check_sour_cream_defense(target_player, card)
                if defense_used:
                    continue  # Skip this player if they defended

                if effect_choice == 'discard_from_borsht': # TODO: card selection
                    # Discard 1 ingredient from target player's borsht
                    if len(self.player_borsht[target_player]) > 0:
                        # For simplicity, we'll discard the first ingredient
                        # In a real implementation, we'd let the player choose
                        discard_card = self.player_borsht[target_player].pop(0)
                        self.discard_pile.append(discard_card)

                elif effect_choice == 'take_from_hand':
                    # Take 1 card from target player's hand
                    if len(self.player_hands[target_player]) > 0:
                        # For simplicity, we'll take the first card
                        # In a real implementation, we'd take a random card
                        taken_card = self.player_hands[target_player].pop(0)
                        self.player_hands[player_id].append(taken_card)

            success = True

        elif effect == 'defense':  # Sour Cream
            # This is handled passively when targeted by Chili or Black Pepper
            return False, "Sour Cream is used defensively when targeted by another player"

        elif effect == 'take_market':  # Ginger
            # Take 2 cards from market
            if len(self.market) < 2:
                return False, "Not enough cards in market"

            if 'market_cards' not in move_data or len(move_data['market_cards']) != 2:
                return False, "Must select 2 market cards"

            selected_cards = move_data['market_cards']
            for card_id in selected_cards:
                for i, card in enumerate(self.market):
                    if card['id'] == card_id:
                        # Remove from market and add to player's hand
                        self.player_hands[player_id].append(card)
                        self.market.pop(i)
                        break

            # Replenish market
            cards_needed = self.game_settings.market_capacity - len(self.market)
            if cards_needed > 0 and len(self.deck) > 0:
                new_cards = self.deck[:cards_needed]
                self.market.extend(new_cards)
                self.deck = self.deck[cards_needed:]

            await self.connection_manager.broadcast(self.room_id, {
                'type': 'special_effect',
                'effect': 'take_market',
                'player_id': player_id,
                'cards_taken': selected_cards
            })

            success = True

        elif effect == 'take_discard':  # Cinnamon
            # Take a card from discard pile
            if len(self.discard_pile) == 0:
                # No cards in discard, return card to hand
                return True, "No cards in discard pile"

            if 'discard_card' not in move_data:
                return False, "Must select a card from discard pile"

            selected_card_id = move_data['discard_card']
            for i, card in enumerate(self.discard_pile):
                if card['id'] == selected_card_id:
                    # Remove from discard and add to player's hand
                    self.player_hands[player_id].append(card)
                    self.discard_pile.pop(i)
                    success = True
                    break

            if not success:
                return False, "Selected card not found in discard pile"

        elif effect == 'look_top_5':  # Olive Oil
            # Look at top 5 cards and take 2
            if len(self.deck) < 5:
                # If not enough cards, shuffle the discard pile
                if len(self.discard_pile) > 0:
                    import random
                    self.deck.extend(self.discard_pile)
                    random.shuffle(self.deck)
                    self.discard_pile = []

            if len(self.deck) < 2:
                return False, "Not enough cards in deck"

            # Look at top 5 cards (or as many as available)
            look_count = min(5, len(self.deck))
            top_cards = self.deck[:look_count]

            if 'selected_cards' not in move_data or len(move_data['selected_cards']) != 2:
                return False, "Must select 2 cards from the top 5"

            # Player selected 2 cards to keep
            selected_indices = []
            for card_id in move_data['selected_cards']:
                for i, card in enumerate(top_cards):
                    if card['id'] == card_id and i not in selected_indices:
                        selected_indices.append(i)
                        self.player_hands[player_id].append(card)
                        break

            if len(selected_indices) != 2:
                return False, "Invalid card selection"

            # Remove selected cards and put the rest back on top of deck
            new_deck = []
            for i, card in enumerate(top_cards):
                if i not in selected_indices:
                    new_deck.append(card)

            self.deck = new_deck + self.deck[look_count:]
            success = True

        elif effect == 'refresh_market':  # Paprika
            await self._handle_market_refresh()

            # Check for 3 identical cards  TODO: add check after each market update
            duplicate_check = {}
            has_duplicates = False

            for card in self.market:
                card_id = card['id']
                if card_id in duplicate_check:
                    duplicate_check[card_id] += 1
                    if duplicate_check[card_id] >= 3:
                        has_duplicates = True
                        break
                else:
                    duplicate_check[card_id] = 1

            if has_duplicates:
                # Refresh market again
                self.discard_pile.extend(self.market)
                self.market = []

                market_size = min(self.game_settings.market_capacity, len(self.deck))
                self.market = self.deck[:market_size]
                self.deck = self.deck[market_size:]

            success = True

        # Remove the card from player's hand and add to discard pile
        self.player_hands[player_id].pop(card_index)
        self.discard_pile.append(card)

        if success:
            await self.connection_manager.broadcast(self.room_id, {
                'type': 'special_played',
                'player_id': player_id,
                'special_card': card_id,
                'effect': effect,
            })

        # Check hand limit and ask player to discard if needed
        limit_success, updated_hand = await self._handle_hand_limit(player_id, self.player_hands[player_id])
        if limit_success:
            self.player_hands[player_id] = updated_hand

        return success, error_message

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

        # Prepare the message
        request_message = {
            'type': request_type,
            'request_id': request_id,
            'timeout': timeout,
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
                response = await asyncio.wait_for(response_future, timeout)  # TODO: Time delay ?
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

    async def _check_sour_cream_defense(self, target_player: int, card=None) -> bool:
        """
        Check if target player has and wants to use a Sour Cream defense card.
        """
        # Check if player has Sour Cream in their hand
        has_sour_cream = False
        sour_cream_index = None

        for i, player_card in enumerate(self.player_hands[target_player]):
            if (
                    player_card['id'] == 'sour_cream'
                    and player_card['type'] == 'special'
                    and player_card['effect'] == 'defense'
            ):
                has_sour_cream = True
                sour_cream_index = i
                break

        if not has_sour_cream:
            return False  # Player doesn't have a defense card

        # Prepare data for defense request
        request_data = {
            'attacker': self.current_player_id,
            'card': card,
            'defense_card': 'sour_cream'
        }

        # Send defense request to player
        response = await self._request_to_player(
            player_id=target_player,
            request_type='defense_request',
            request_data=request_data,
            timeout=30
        )

        # Check if player chose to use defense
        defense_used = response.get('use_defense', False) and not response.get('timed_out', False)

        if defense_used:
            # Remove Sour Cream from player's hand and put it in discard pile
            defense_card = self.player_hands[target_player].pop(sour_cream_index)
            self.discard_pile.append(defense_card)

            # Notify all players about the defense
            await self.connection_manager.broadcast(self.room_id, {
                'type': 'card_defended',
                'defender': target_player,
                'attacker': self.current_player_id,
                'defense_card': 'sour_cream'
            })

        return defense_used

    async def _handle_market_limit(self) -> None:
        if len(self.market) < self.game_settings.market_capacity:
            await self._handle_market_refill()
        if len(self.market) > self.game_settings.market_capacity:
            # Calculate how many cards need to be discarded
            cards_to_discard = len(self.market) - self.game_settings.market_capacity

            # Prepare request data
            request_data = {
                'market': self.market,
                'discard_count': cards_to_discard,
                'reason': 'market_limit',
            }

            # Send discard selection request to player
            response = await self._request_to_player(
                player_id=self.current_player_id,
                request_type='discard_selection',
                request_data=request_data,
                timeout=30  # 30 second timeout
            )

            # Create copies of the hand for manipulation
            updated_market = self.market.copy()
            discarded_cards = []

            # Process the response
            if response.get('timed_out', False) or response.get('random_discard', False):
                # discard random cards
                discard_indices = random.sample(range(len(self.market)), cards_to_discard)
                discard_indices.sort(reverse=True)  # Sort in reverse to avoid index shifting

                # Remove cards from hand and add to discard pile
                for idx in discard_indices:
                    discarded_cards.append(updated_market[idx])
                    updated_market.pop(idx)

            else:
                # Get player's selected cards to discard
                selected_card_ids = response.get('selected_cards', [])

                # Validate selection
                if len(selected_card_ids) != cards_to_discard:
                    # Invalid selection, fall back to random
                    await self._handle_market_limit()
                    return

                # Process each selected card
                for card_uid in selected_card_ids:
                    card_found = False
                    for i, card in enumerate(updated_market):
                        if card['uid'] == card_uid:
                            discarded_cards.append(card)
                            updated_market.pop(i)
                            card_found = True
                            break

                    if not card_found:
                        # Card not found, invalid selection
                        await self._handle_market_limit()
                        return

            # Add discarded cards to discard pile
            self.discard_pile.extend(discarded_cards)

            # Notify about discard
            await self.connection_manager.broadcast(self.room_id, {
                'type': 'cards_from_market_discarded',
                'cards': [card['id'] for card in discarded_cards]
            })
            self.market = updated_market

    async def _handle_market_refresh(self, cards_to_discard=None) -> None:
        """
        Discard all current market cards and replace them with new cards from the deck.
        """
        # Move selected or all current market cards to discard pile
        cards = cards_to_discard or self.market

        for card in cards:
            self.market.remove(card)
        self.discard_pile.extend(cards)

        await self.connection_manager.broadcast(self.room_id, {
            'type': 'market_cards_discarded',
            'cards': cards,
        })

        await self._handle_market_refill()

    async def _handle_market_refill(self) -> None:
        cards_to_add = self.game_settings.market_capacity - len(self.market)

        # Check if we need to reshuffle the deck
        if len(self.deck) < cards_to_add and len(self.discard_pile) > 0:
            self._reshuffle_discard()

        # Get new cards from deck
        new_cards = self.deck[:cards_to_add]
        self.market = self.market.extend(new_cards)
        self.deck = self.deck[cards_to_add:]

        await self.connection_manager.broadcast(self.room_id, {
            'type': 'market_cards_added',
            'cards': new_cards,
        })

    async def _handle_put_cards_to_market(self, cards):
        self.market.extend(cards)

        if len(self.market) > self.game_settings.market_capacity:
            cards_to_discard = self.game_settings.market_capacity - len(self.market)
            cards = self.market[cards_to_discard:]
            await self._handle_market_refresh(cards)

    def _reshuffle_discard(self) -> None:
        """
        Reshuffle discard pile into the ingredient deck.
        Skip shkvarka cards if present.
        """
        # Filter out shkvarka cards if applicable
        regular_cards = [card for card in self.discard_pile
                         if 'type' in card and card['type'] != 'shkvarka']

        # Shuffle the regular cards and add to deck
        random.shuffle(regular_cards)
        self.deck.extend(regular_cards)

        # Clear discard pile (keeping only shkvarkas)
        self.discard_pile = [card for card in self.discard_pile
                             if 'type' in card and card['type'] == 'shkvarka']

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

        # Replenish market if needed
        cards_needed = self.game_settings.market_capacity - len(self.market)
        if cards_needed > 0 and len(self.deck) > 0:
            new_cards = self.deck[:cards_needed]
            self.market.extend(new_cards)
            self.deck = self.deck[cards_needed:]

        await self.connection_manager.broadcast(self.room_id, {
            'type': 'ingredients_exchanged',
            'player_id': player_id,
            'hand_cards': hand_cards,
            'market_cards': market_cards,
        })

        success, updated_hand = await self._handle_hand_limit(player_id, self.player_hands[player_id])
        if success:
            self.player_hands[player_id] = updated_hand

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
            current_player = self.players[self.current_player_index]
            if str(current_player) == str(self.first_finisher):
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
            completed_ingredients = [ing for ing in recipe_ingredients if ing in player_ingredients]
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
            completed_ingredients = [ing for ing in recipe_ingredients if ing in player_ingredients]
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
        return

    async def resend_pending_requests(self, user_id: int) -> None:
        for request in self.pending_requests.get(user_id, dict()):
            await self.connection_manager.send(self.room_id, user_id, self.sent_requests[request])

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
            first_finisher=self.first_finisher,
            market_limit=self.game_settings.market_capacity,
            recipes_revealed=self.recipes_revealed,
            cards_in_deck=len(self.deck),

            # Market information
            market=self.market.copy(),
            free_refresh=self._is_market_free_refresh_available(),

            # Discard pile - only show top card
            discard_pile_size=len(self.discard_pile),
            discard_pile_top=self.discard_pile[-1] if self.discard_pile else None,

            # Player-specific information
            your_hand=self.player_hands[player_id].copy(),
            your_borsht=self.player_borsht[player_id].copy(),
            your_recipe=self.player_recipes[player_id].copy(),

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

        # If game is over, include final scores
        if self.is_game_over:
            state["winner"] = self.winner
            state["scores"] = self.calculate_scores()

            # Once game is over, reveal all player recipes
            for pid in self.players:
                if pid not in state["players"]:
                    state["players"][pid] = {}
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
            completed_ingredients = [ing for ing in recipe_ingredients if ing in player_ingredient_ids]
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
            "winner": winner_id,
            "winner_score": scores[winner_id],
            "scores": scores,
            "player_stats": player_stats,
            "first_finisher": self.first_finisher,
            "cards_remaining_in_deck": len(self.deck),
            "cards_in_discard": len(self.discard_pile),
            "active_shkvarkas": len(self.active_shkvarkas),
            "player_count": len(self.players)
        }

        return game_stats
