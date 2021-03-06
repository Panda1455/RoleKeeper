# The MIT License (MIT)
# Copyright (c) 2017 Levak Borok <levak92@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

import discord
import asyncio
import csv
import random
import io

from team import Team, TeamCaptain
from match import Match, MatchBo2, MatchBo3
from inputs import sanitize_input, translit_input
from db import open_db

welcome_message_bo1 =\
"""
Welcome {m_teamA} and {m_teamB}!
-- Match **BEST OF 1** --
This text channel will be used by the judge and team captains to exchange anything about the match between teams {teamA} and {teamB}.
This sequence is made using the `!ban` command team by team until one remains.
Last team to ban also needs to chose the side they will play on using `!side xxxx` (attack or defend).

For instance, team A types `!ban Pyramid` which will then ban the map _Pyramid_ from the match, team B types `!ban d17` which will ban the map D-17, and so on, until only one map remains. team B then picks the side using `!side attack`.
"""

welcome_message_bo2 =\
"""
Welcome {m_teamA} and {m_teamB}!
-- Match **BEST OF 2** --
This text channel will be used by the judge and team captains to exchange anything about the match between teams {teamA} and {teamB}.
This sequence is made using the `!pick`, `!ban` and `!side` commands one by one using the following order:

 - {teamA} bans, {teamB} bans,
 - {teamA} picks, {teamB} picks,
 - {teamB} picks the side (attack or defend).

For instance, team A types `!ban Yard` which will then ban the map _Yard_ from the match, team B types `!ban d17` which will ban the map D-17. team A would then type `!pick Destination`, picking the first map and so on, until only one map remains, which will be the tie-breaker map. team B then picks the side using `!side attack`.
"""

welcome_message_bo3 =\
"""
Welcome {m_teamA} and {m_teamB}!
-- Match **BEST OF 3** --
This text channel will be used by the judge and team captains to exchange anything about the match between teams {teamA} and {teamB}.
This sequence is made using the `!pick`, `!ban` and `!side` commands one by one using the following order:

 - {teamA} bans, {teamB} bans,
 - {teamA} picks, {teamB} picks,
 - {teamA} bans, {teamB} bans,
 - Last map remaining is the draw map,
 - {teamB} picks the side (attack or defend).

For instance, team A types `!ban Yard` which will then ban the map _Yard_ from the match, team B types `!ban d17` which will ban the map D-17. team A would then type `!pick Destination`, picking the first map and so on, until only one map remains, which will be the tie-breaker map. team B then picks the side using `!side attack`.
"""

import atexit

class RoleKeeper:
    def __init__(self, client, config):
        self.client = client
        self.config = config
        self.db = {}
        atexit.register(self.atexit)

    def atexit(self):
        if self.db:
            for server, db in self.db.items():
                print ('Closing DB "{}"'.format(server.name))
                db.close()
            self.db = None

    def check_server(self, server):
        if server.name not in self.config['servers']:
            print ('WARNING: Server "{}" not configured!'.format(server.name))
            return False
        return True

    # Parse members from CSV file
    def parse_teams(self, server, filepath): # TODO cup
        captains = {}
        groups = {}

        self.db[server]['roles'] = {}

        with open(filepath) as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in reader:
                # Skip empty lines and lines starting with #
                if len(row) <= 0 or row[0].startswith('#'):
                    continue

                discord_id = row[0].strip()
                team_name = row[1].strip()
                nickname = row[2].strip()
                group_id = row[3].strip() # TODO test what happens with empty group

                captains[discord_id] = \
                    TeamCaptain(discord_id, team_name, nickname, group_id)

                # If group is new to us, cache it
                if group_id not in groups:
                    group_name = self.config['roles']['group'].format(group_id) # TODO cup
                    group = discord.utils.get(server.roles, name=group_name)
                    print('{id}: {g}'.format(id=group_id, g=group))
                    groups[group_id] = group
                    self.cache_role(server, group_name)

        print('Parsed teams:')
        # Print parsed members
        for m in captains:
            print('-> {}'.format(captains[m]))

        self.db[server]['captains'] = captains # TODO Add cup
        self.db[server]['groups'] = groups # TODO cup/ref?

    def open_db(self, server):
        if server in self.db and self.db[server]:
            self.db[server].close()

        self.db[server] = open_db(self.config['servers'][server.name]['db'])

        if 'matches' not in self.db[server]:
            self.db[server]['matches'] = {}

        if 'teams' not in self.db[server]:
            self.db[server]['teams'] = {}

        if 'captains' not in self.db[server]:
            self.db[server]['captains'] = {}

        if 'groups' not in self.db[server]:
            self.db[server]['groups'] = {}

        if 'roles' not in self.db[server]:
            self.db[server]['roles'] = {}

        if 'sroles' not in self.db[server]:
            self.db[server]['sroles'] = {}

        # Refill group cache
        self.db[server]['sroles'] = {}
        self.cache_special_role(server, 'captain')
        self.cache_special_role(server, 'referee')
        self.cache_special_role(server, 'streamer')

    # Acknowledgement that we are succesfully connected to Discord
    async def on_ready(self):

        for server in self.client.servers:
            print('Server: {}'.format(server))

            if self.check_server(server):
                self.open_db(server)

            #await self.refresh(server)

    async def on_dm(self, message):
        # If it is us sending the DM, exit
        if message.author == self.client.user:
            return

        print('PM from {}: {}'.format(message.author, message.content))

        # Apologize
        await self.reply(message,
                       ''':wave: Hello there!
                       I am sorry, I cannot answer your question, I am just a bot!
                       Feel free to ask a referee or admin instead :robot:''')

    async def on_member_join(self, member):
        if member.server.name not in self.config['servers']:
            return

        await self.handle_member_join(member)

    def cache_special_role(self, server, role_id):
        role_name = self.config['roles'][role_id]
        role = discord.utils.get(server.roles, name=role_name)
        self.db[server]['sroles'][role_id] = role
        if not self.db[server]['sroles'][role_id]:
            print ('WARNING: Missing role "{}" in {}'.format(role_name, server.name))

    def get_special_role(self, server, role_id):
        if role_id in self.db[server]['sroles']:
            return self.db[server]['sroles'][role_id]
        return None

    def cache_role(self, server, role_id):
        role = discord.utils.get(server.roles, name=role_id)
        self.db[server]['roles'][role_id] = role
        if not self.db[server]['roles'][role_id]:
            print ('WARNING: Missing role "{}" in {}'.format(role_id, server.name))

    def get_role(self, server, role_id):
        if role_id in self.db[server]['roles']:
            return self.db[server]['roles'][role_id]
        return None

    async def add_captain(self, message, server, member, team, nick, group): # TODO cup
        if not self.check_server(server):
            return

        discord_id = str(member)

        # If captain already exists, remove him
        if discord_id in self.db[server]['captains']:
            await self.remove_captain(message, server, member)

        # Check if destination group exists
        if group not in self.db[server]['groups']:
            await self.reply(message, 'Group "{}" does not exist'.format(group))
            return

        # Add new captain to the list
        self.db[server]['captains'][discord_id] = \
            TeamCaptain(discord_id, team, nick, group)

        # Trigger update on member
        await self.handle_member_join(member)

    async def remove_captain(self, message, server, member):
        if not self.check_server(server):
            return

        discord_id = str(member)

        if discord_id not in self.db[server]['captains']:
            await self.reply(message, '{} is not a known captain'.format(member.mention))
            return

        captain = self.db[server]['captains'][discord_id]

        captain_role = self.get_special_role(server, 'captain') # TODO cup, which cup? not special?
        group_role = self.db[server]['groups'][captain.group]
        team_role = captain.team

        crole_name = captain_role.name if captain_role else ''
        grole_name = group_role.name if group_role else ''
        trole_name = team_role.name if team_role else ''

        # Remove team, team captain and group roles from member
        try:
            await self.client.remove_roles(member, captain_role, group_role, team_role)
            print ('Remove roles "{crole}", "{grole}" and "{trole}" from "{member}"'\
                   .format(member=discord_id,
                           crole=crole_name,
                           grole=grole_name,
                           trole=trole_name))

            del self.db[server]['teams'][trole_name]
        except:
            print ('WARNING: Failed to remove roles "{crole}", "{grole}" and "{trole}" from "{member}"'\
                   .format(member=discord_id,
                           crole=crole_name,
                           grole=grole_name,
                           trole=trole_name))
            pass

        # Check if the role is now orphan, and delete it
        if not any(r == team_role for m in server.members for r in m.roles):
            try:
                await self.client.delete_role(server, team_role)
                print ('Deleted role "{role}"'\
                       .format(role=trole_name))
            except:
                print ('WARNING: Failed to delete role "{role}"'\
                       .format(role=trole_name))
                pass


        # Reset member nickname
        try:
            await self.client.change_nickname(member, None)
            print ('Reset nickname for "{member}"'\
                   .format(member=discord_id))
        except:
            print ('WARNING: Failed to reset nickname for "{member}"'\
                   .format(member=discord_id))
            pass

        # Remove captain from DB
        del self.db[server]['captains'][discord_id]

    # Refresh internal structures
    # 1. Reparse team captain file
    # 2. Refill group cache
    # 3. Visit all members with no role
    async def refresh(self, server):
        if not self.check_server(server):
            return

        # TODO cups

        # TODO remove, use CSV upload instead
        # Reparse team captain file
        self.parse_teams(server, self.config['servers'][server.name]['captains'])
        await self.create_all_roles(server)

        # Visit all members with no role
        for member in server.members:
            if len(member.roles) == 1:
                print('- Member without role: {}'.format(member))
                await self.handle_member_join(member)

    # Go through the parsed captain list and create all team roles
    # TODO remove this
    async def create_all_roles(self, server):
        if not self.check_server(server):
            return

        self.db[server]['teams'] = {}
        for _, captain in self.db[server]['captains'].items():
            role = await self.create_team_role(server, captain.team_name)
            captain.team = role

    # Create team captain role
    async def create_team_role(self, server, team_name):
        role_name = self.config['roles']['team'].format(team_name)

        if role_name in self.db[server]['teams']:
            return self.db[server]['teams'][role_name].role

        role = discord.utils.get(server.roles, name=role_name)

        if not role:
            role = await self.client.create_role(
                server,
                name=role_name,
                permissions=discord.Permissions.none(),
                mentionable=True)

            print('Create new role <{role}>'\
                  .format(role=role_name))

        role.name = role_name # This is a hotfix

        self.db[server]['teams'][role_name] = Team(team_name, role)

        return role

    # Whenever a new member joins into the Discord server
    # 1. Create a user group just for the Team captain
    # 2. Assign the special group to that Team captain
    # 3. Assign the global group to that Team captain
    # 4. Change nickname of Team captain
    async def handle_member_join(self, member):
        discord_id = str(member)
        server = member.server

        # TODO find cup from discord_id

        if discord_id not in self.db[server]['captains']:
            print('WARNING: New user "{}" not in captain list'\
                  .format(discord_id))
            return

        print('Team captain "{}" joined server'\
              .format(discord_id))

        captain = self.db[server]['captains'][discord_id]

        # Create role
        team_role = await self.create_team_role(server, captain.team_name) # TODO cup
        captain.team = team_role

        # Assign user roles
        group_role = self.db[server]['groups'][captain.group]
        captain_role = self.get_special_role(server, 'captain') # TODO cup, which cup? not special?

        if team_role and captain_role and group_role:
            await self.client.add_roles(member, team_role, captain_role, group_role)
        else:
            print('ERROR: Missing one role out of R:{} C:{} G:{}'\
                  .format(team_role, captain_role, group_role))

        print('Assigned role <{role}> to "{id}"'\
              .format(role=team_role.name, id=discord_id))

        # Change nickname of team captain
        nickname = '{}'.format(captain.nickname)

        try:
            await self.client.change_nickname(member, nickname)
            print ('Renamed "{id}" to "{nick}"'\
                   .format(id=discord_id, nick=nickname))
        except:
            print ('WARNING: Failed to rename "{id}" to "{nick}"'\
                   .format(id=discord_id, nick=nickname))
            pass

    # Reply to a message in a channel
    async def reply(self, message, reply):
        return await self.client.send_message(
            message.channel,
            '{} {}'.format(message.author.mention, reply))

    MATCH_BO1 = 1
    MATCH_BO2 = 2
    MATCH_BO3 = 3

    # Create a match against 2 teams
    # 1. Create the text channel
    # 2. Add permissions to read/send to both teams, and the judge
    # 3. Send welcome message
    # 4. Register the match to internal logic for commands like !ban x !pick x
    async def matchup(self, message, server, _roleteamA, _roleteamB, mode=MATCH_BO1): # TODO cup
        if not self.check_server(server):
            return

        randomized = [ _roleteamA, _roleteamB ]
        random.shuffle(randomized)
        roleteamA, roleteamB = randomized[0], randomized[1]

        notfound = None

        if roleteamA.name in self.db[server]['teams']:
            teamA = self.db[server]['teams'][roleteamA.name]
        else:
            notfound = roleteamA.name

        if roleteamB.name in self.db[server]['teams']:
            teamB = self.db[server]['teams'][roleteamB.name]
        else:
            notfound = roleteamB.name

        if notfound:
            await self.reply(message, 'Role "{}" is not a known team'.format(notfound))
            return

        roleteamA_name_safe = sanitize_input(translit_input(teamA.name))
        roleteamB_name_safe = sanitize_input(translit_input(teamB.name))
        channel_name = 'match_{}_vs_{}'.format(roleteamA_name_safe, roleteamB_name_safe)  # TODO cup
        topic = 'Match {} vs {}'.format(teamA.name, teamB.name)

        ref_role = self.get_special_role(server, 'referee')

        read_perms = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        no_perms = discord.PermissionOverwrite(read_messages=False)

        channel = discord.utils.get(server.channels, name=channel_name)

        if not channel:
            try:
                channel = await self.client.create_channel(
                    server,
                    channel_name,
                    (roleteamA, read_perms),
                    (roleteamB, read_perms),
                    (server.default_role, no_perms),
                    (server.me, read_perms),
                    (ref_role, read_perms))

                print('Created channel "<{channel}>"'\
                      .format(channel=channel.name))
            except:
                print('WARNING: Failed to create channel "<{channel}>"'\
                      .format(channel=channel.name))

            try:
                await self.client.edit_channel(
                    channel,
                    topic=topic)

                print('Set topic for channel "<{channel}>" to "{topic}"'\
                      .format(channel=channel.name, topic=topic))
            except:
                print('WARNING: Failed to set topic for channel "<{channel}>"'\
                      .format(channel=channel.name))
        else:
            print('Reusing existing channel "<{channel}>"'\
                  .format(channel=channel.name))

        maps = self.config['servers'][server.name]['maps']

        if mode == self.MATCH_BO3:
            match = MatchBo3(roleteamA, roleteamB, maps)
            template = welcome_message_bo3
        elif mode == self.MATCH_BO2:
            match = MatchBo2(roleteamA, roleteamB, maps)
            template = welcome_message_bo2
        else:
            match = Match(roleteamA, roleteamB, maps)
            template = welcome_message_bo1

        self.db[server]['matches'][channel_name] = match
        handle = Handle(self, None, channel)
        msg = template.format(m_teamA=roleteamA.mention,
                              m_teamB=roleteamB.mention,
                              teamA=teamA.name,
                              teamB=teamB.name,
                              maps='\n'.join([ ' - {}'.format(m) for m in maps ]))

        await self.client.send_message(channel, msg)
        await match.begin(handle)

    # Returns if a member is a team captain in the given channel
    def is_captain_in_match(self, member, channel):
        server = member.server

        if server not in self.db:
            return False

        if channel.name not in self.db[server]['matches']:
            return False

        return self.db[server]['matches'][channel.name].is_in_match(member)

    # Ban a map
    async def ban_map(self, member, channel, map_unsafe, force=False):
        server = member.server
        banned_map_safe = sanitize_input(translit_input(map_unsafe))

        if not self.check_server(server):
            return

        if channel.name not in self.db[server]['matches']:
            return

        handle = Handle(self, member, channel)
        await self.db[server]['matches'][channel.name].ban_map(handle, banned_map_safe, force)

    # Pick a map
    async def pick_map(self, member, channel, map_unsafe, force=False):
        server = member.server
        picked_map_safe = sanitize_input(translit_input(map_unsafe))

        if not self.check_server(server):
            return

        if channel.name not in self.db[server]['matches']:
            return

        handle = Handle(self, member, channel)
        await self.db[server]['matches'][channel.name].pick_map(handle, picked_map_safe, force)

    # Choose sides
    async def choose_side(self, member, channel, side_unsafe, force=False):
        server = member.server
        side_safe = sanitize_input(translit_input(side_unsafe))

        if not self.check_server(server):
            return

        if channel.name not in self.db[server]['matches']:
            return

        handle = Handle(self, member, channel)
        await self.db[server]['matches'][channel.name].choose_side(handle, side_safe, force)

    # Broadcast information that the match is or will be streamed
    # 1. Notify captains match will be streamed
    async def stream_match(self, message, match_id):
        server = message.server

        if not self.check_server(server):
            return

        member = message.author
        channel = discord.utils.get(member.server.channels, name=match_id)

        # If we found a channel with the given name
        if channel:

            # 1. Notify captains match will be streamed
            await self.client.send_message(
                channel, ':eye::popcorn: _**{}** will stream this match!_ :movie_camera::satellite:\n'
                ':arrow_forward: _8.6 Teams participating in a streamed match get an additional 10 minutes to prepare; the time of the match may change per the decision of the Staff/Organizers._\n'\
                .format(member.nick if member.nick else member.name))
            await self.reply(message, 'roger!')

            print('Notified "{channel}" the match will be streamed by "{member}"'\
                  .format(channel=channel.name,
                          member=str(member)))
        else:
            await self.reply(message, 'This match does not exist!')


    # Remove all teams
    # 1. Delete all existing team roles
    # 2. Find all members with role team captain
    # 3. Remove group role from member
    # 4. Remove team captain and group roles from member
    # 5. Reset member nickname
    async def wipe_teams(self, server):
        if not self.check_server(server):
            return

        captain_role = self.get_special_role(server, 'captain') # TODO cup, not special?

        # 1. Delete all existing team roles
        for role_name, team in self.db[server]['teams'].items():
            try:
                await self.client.delete_role(server, team.role)
                print ('Deleted role "{role}"'\
                       .format(role=role_name))
            except:
                print ('WARNING: Failed to delete role "{role}"'\
                       .format(role=role_name))
                pass

        self.db[server]['teams'].clear()

        # 2. Find all members with role team captain
        for member in server.members: # TODO go through db instead
            discord_id = str(member)
            if discord_id not in self.db[server]['captains']: # TODO cup
                continue

            captain = self.db[server]['captains'][discord_id] # TODO cup

            print ('Found captain "{member}"'\
                   .format(member=discord_id))

            # 3. Remove group role from member
            group_role = self.db[server]['groups'][captain.group] \
                         if captain.group in self.db[server]['groups'] \
                         else None

            crole_name = captain_role.name
            grole_name = group_role.name if group_role else '<no group>'

            # 4. Remove team captain and group roles from member
            try:
                await self.client.remove_roles(member, captain_role, group_role)
                print ('Remove roles "{crole}" and "{grole}" from "{member}"'\
                       .format(member=discord_id,
                               crole=crole_name,
                               grole=grole_name))
            except:
                print ('WARNING: Failed to remove roles "{crole}" and "{grole}" from "{member}"'\
                       .format(member=discord_id,
                               crole=crole_name,
                               grole=grole_name))
                pass

            # 5. Reset member nickname
            try:
                await self.client.change_nickname(member, None)
                print ('Reset nickname for "{member}"'\
                       .format(member=discord_id))
            except:
                print ('WARNING: Failed to reset nickname for "{member}"'\
                       .format(member=discord_id))
                pass

        self.db[server]['captains'].clear() # TODO cup

    # Remove all match rooms
    # 1. Find all match channels that where created by the bot for this cup
    # 2. Delete channel
    async def wipe_matches(self, server):
        if not self.check_server(server):
            return

        for channel_name in self.db[server]['matches'].keys(): # TODO cup
            channel = discord.utils.get(server.channels, name=channel_name)
            if channel:
                try:
                    await self.client.delete_channel(channel)
                    print ('Deleted channel "{channel}"'\
                           .format(channel=channel_name))
                except:
                    print ('WARNING: Fail to Delete channel "{channel}"'\
                           .format(channel=channel_name))

        self.db[server]['matches'].clear() # TODO cup

    # Remove all messages that are not pinned in a given channel
    async def wipe_messages(self, message, channel):
        server = message.server

        if not self.check_server(server):
            return

        count = 0
        try:
            messages_to_delete = [
                msg async for msg in self.client.logs_from(channel) if not msg.pinned ]
            count = len(messages_to_delete)
        except:
            print('WARNING: No permission to read logs from "{}"'.format(channel.name))
            return

        reply = await self.reply(message,
                                 'Clearing {count} message(s)... (this might take a while)'\
                                 .format(count=count))

        for msg in messages_to_delete:
            try:
                await self.client.delete_message(msg)
            except:
                count = count - 1
                print('WARNING: No permission to delete in "{}"'.format(channel.name))
                pass

        await self.client.edit_message(reply, '{mention} Deleted {count} messages.'\
                                       .format(mention=message.author.mention,
                                               count=count))
        print ('Deleted {count} messages in "{channel}"'\
               .format(count=count, channel=channel.name))

    # Announcement message
    async def announce(self, msg, message):
        server = message.server

        if not self.check_server(server):
            return

        handle = Handle(self, message.author, message.channel)
        await handle.broadcast('announcement', msg)

    # Export full list of members as CSV
    async def export_members(self, msg, message):
        server = message.server

        if not self.check_server(server):
            return

        csv = io.BytesIO()
        csv.write('#discord_id\n'.encode())

        for member in server.members:
            discord_id = str(member)
            csv.write('{}\n'.format(discord_id).encode())

        csv.seek(0)

        member_count = len(server.members)
        filename = 'members-{}.csv'.format(self.config['servers'][server.name]['db'])
        msg = '{mention} Here is the list of all {count} members in this Discord server'\
            .format(mention=message.author.mention,
                    count=member_count)

        try:
            await self.client.send_file(message.channel,
                                        csv,
                                        filename=filename,
                                        content=msg)
            print ('Sent member list ({})'.format(member_count))
        except Exception as e:
            print ('ERROR: Failed to send member list ({})'.format(member_count))
            raise e

        csv.close()


class Handle:
    def __init__(self, bot, member, channel):
        self.bot = bot
        self.member = member
        self.channel = channel

        self.team = None

        if member:
            try:
                self.team = bot.db[member.server]['captains'][str(member)].team # TODO cup
            except KeyError:
                pass

    async def reply(self, msg):
        return await self.send('{} {}'.format(self.member.mention, msg))

    async def send(self, msg):
        try:
            return await self.bot.client.send_message(self.channel, msg)
        except discord.errors.HTTPException as e:
            print('WARNING: HTTPexception: {}'.format(str(e)))
            await asyncio.sleep(10)
            return await self.send(msg)

    async def broadcast(self, bcast_id, msg):
        channels = []
        try:
            channels = self.bot.config['servers'][self.channel.server.name]['rooms'][bcast_id]
        except:
            print('WARNING: No broadcast configuration for "{}"'.format(bcast_id))
            pass

        for channel_name in channels:
            channel = discord.utils.get(self.channel.server.channels, name=channel_name)
            if channel:
                try:
                    await self.bot.client.send_message(channel, msg)
                except:
                    print('WARNING: No permission to write in "{}"'.format(channel_name))
                    pass
            else:
                print ('WARNING: Missing channel {}'.format(channel_name))
