#! /usr/bin/env python3

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
import sys

from rolekeeper import RoleKeeper

import json

def get_config(path):
    try:
        with open(path, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError as e:
        print('ERROR while loading config.\n{}: "{}"'\
              .format(e.strerror, e.filename))
        return None
    except Exception as e:
        print('ERROR while loading config.\n{}: line {} col {}'\
              .format(e.msg, e.lineno, e.colno))
        return None

client = discord.Client()

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    await rk.on_ready()

@client.event
async def on_member_join(member):
    await rk.on_member_join(member)

@client.event
async def on_message(message):
    # If message is a DM
    if type(message.author) is discord.User:
        await rk.on_dm(message)
        return

    is_admin = message.author.server_permissions.manage_roles
    is_ref = discord.utils.get(message.author.roles, name=rk.config['roles']['referee']) or is_admin
    is_captain_in_match = rk.is_captain_in_match(message.author, message.channel) or is_admin or is_ref
    is_streamer = discord.utils.get(message.author.roles, name=rk.config['roles']['streamer']) or is_admin

    if len(message.content) <= 0:
        return

    command = message.content.split()[0]
    args = message.content.replace(command, '', 1).strip()

    # ADMIN COMMANDS
    #----------------

    if command == '!refresh' and is_admin:
        await rk.refresh(message.author.server)
    elif command == '!create_teams' and is_admin:
        await rk.create_all_roles(message.author.server)

    elif command == '!wipe_teams' and is_admin:
        await rk.wipe_teams(message.author.server)

    elif command == '!wipe_matches' and is_admin:
        await rk.wipe_matches(message.author.server)

    elif command == '!wipe_messages' and is_admin:
        if len(message.channel_mentions) < 1:
            await rk.reply(message,
                           'Not enough arguments:\n```!wipe_messages #channel```')
        else:
            await rk.wipe_messages(message, message.channel_mentions[0])

    elif command == '!announce' and is_admin:
        await rk.announce(args, message)

    elif command == '!members' and is_admin:
        await rk.export_members(args, message)

    # REF COMMANDS
    #--------------

    elif command == '!add_captain' and is_ref:
        parts = args.split()
        if len(message.mentions) == 1 and len(parts) >= 4:
            await rk.add_captain(message,
                                 message.author.server,
                                 message.mentions[0], # TODO check it's the first argument?
                                 parts[1],
                                 parts[2],
                                 parts[3])
        else:
            await rk.reply(message,
                           'Too much or not enough arguments:\n```!add_captain @xxx team nick group```')

    elif command == '!remove_captain' and is_ref:
        if len(message.mentions) == 1:
            await rk.remove_captain(message,
                                    message.author.server,
                                    message.mentions[0])
        else:
            await rk.reply(message,
                           'Too much or not enough arguments:\n```!remove_captain @xxx```')

    elif command == '!bo1' and is_ref:
        if len(message.role_mentions) == 2:
            await rk.matchup(message,
                             message.author.server,
                             message.role_mentions[0],
                             message.role_mentions[1],
                             mode=RoleKeeper.MATCH_BO1)
        else:
            await rk.reply(message,
                           'Too much or not enough arguments:\n```!bo1 @xxx @yyy```')

    elif command == '!bo2' and is_ref:
        if len(message.role_mentions) == 2:
            await rk.matchup(message,
                             message.author.server,
                             message.role_mentions[0],
                             message.role_mentions[1],
                             mode=RoleKeeper.MATCH_BO2)
        else:
            await rk.reply(message,
                           'Too much or not enough arguments:\n```!bo2 @xxx @yyy```')

    elif command == '!bo3' and is_ref:
        if len(message.role_mentions) == 2:
            await rk.matchup(message,
                             message.author.server,
                             message.role_mentions[0],
                             message.role_mentions[1],
                             mode=RoleKeeper.MATCH_BO3)
        else:
            await rk.reply(message,
                           'Too much or not enough arguments:\n```!bo3 @xxx @yyy```')

    elif command == '!say' and is_ref:
        parts = args.split()
        if len(parts) <= 1:
            await rk.reply(message,
                           'Not enough arguments:\n```!say #channel message...```')
        else:
            channel_id = parts[0]
            if channel_id.startswith('<'):
                channel_id = channel_id[2:-1]
                channel = discord.utils.get(message.author.server.channels, id=channel_id)
            else:
                channel = discord.utils.get(message.author.server.channels, name=channel_id)

            if channel:
                msg = args.replace(parts[0], '', 1)
                try:
                    await rk.client.send_message(channel, msg)
                except:
                    await rk.reply(message,
                                   'I do not see channel `#{}`'.format(channel.name))
            else:
                await rk.reply(message,
                               'No channel named `#{}`'.format(channel_id))


    # CAPTAIN COMMANDS
    #-------------------


    elif command == '!ban' and is_captain_in_match:
        await rk.ban_map(message.author,
                         message.channel,
                         args.split()[0] if len(args) > 0 else '',
                         force=is_ref)

    elif command == '!pick' and is_captain_in_match:
        await rk.pick_map(message.author,
                          message.channel,
                          args.split()[0] if len(args) > 0 else '',
                          force=is_ref)

    elif command == '!side'  and is_captain_in_match:
        await rk.choose_side(message.author,
                             message.channel,
                             args.split()[0] if len(args) > 0 else '',
                             force=is_ref)

    # STREAMER COMMANDS
    #-------------------

    elif command == '!stream' and is_streamer:
        await rk.stream_match(message,
                              args.split()[0] if len(args) > 0 else '')

if __name__ == '__main__':

    config = None

    if len(sys.argv) > 1:
        config = get_config(sys.argv[1])
    else:
        print('Using default configuration file path: `config.json`')
        config = get_config('config.json')

    if config:
        rk = RoleKeeper(client, config)
        client.run(config['app_bot_token'])
