import re
from urllib.parse import quote

import discord
from discord.ext import commands

from bot import is_lastfm_album_url


def _artist_name(artist):
    if isinstance(artist, dict):
        return artist.get("name", "")
    return artist or ""


def _album_lastfm_url(item):
    if url := item.get("url"):
        return url
    artist = _artist_name(item.get("artist"))
    album = item.get("title", "")
    if artist and album:
        return f"https://www.last.fm/music/{quote(artist, safe='')}/+/{quote(album, safe='')}"
    return None


_SNOWFLAKE_RE = re.compile(r"\s(\d{17,20})$")


def _parse_suggested_user_id(raw: str) -> tuple[str, int | None]:
    match = _SNOWFLAKE_RE.search(raw)
    if not match:
        return raw, None
    return raw[: match.start()].strip(), int(match.group(1))


async def _resolve_user_name(bot, guild, user_id: int) -> str:
    if guild and (member := guild.get_member(user_id)):
        return member.display_name
    try:
        user = await bot.fetch_user(user_id)
        return user.display_name
    except (discord.NotFound, discord.HTTPException):
        return str(user_id)


def _album_title_link(item):
    title = item.get("title", "Unknown")
    url = _album_lastfm_url(item)
    if url:
        return f"[{title}]({url})"
    return title


def register_commands(bot):
    @bot.group(name="aotw", invoke_without_command=True)
    async def aotw(ctx):
        await ctx.send(
            "`!aotw normal add`, `!aotw normal queue`, `!aotw bonus add`, `!aotw bonus queue`, `!aotw help`"
        )

    @aotw.group(name="normal", invoke_without_command=True)
    async def normal(ctx):
        await ctx.send("`!aotw normal add`, `!aotw normal queue`")

    @aotw.group(name="bonus", invoke_without_command=True)
    async def bonus(ctx):
        await ctx.send("`!aotw bonus add`, `!aotw bonus queue`")

    @aotw.command(name="help")
    async def aotw_help(ctx):
        embed = discord.Embed(title="AOTW Commands", color=0x3498DB)
        embed.add_field(
            name="!aotw <queue> add <query|last.fm URL> [user_id]",
            value="Search Last.fm or pass a Last.fm album URL to add an album to the selected queue. Optionally append another user's Discord ID as the suggester.",
            inline=False,
        )
        embed.add_field(
            name="!aotw <queue> queue",
            value="Show the selected queue.",
            inline=False,
        )
        embed.add_field(
            name="!aotw <queue> remove <index>",
            value="Remove an album from the selected queue by its index.",
            inline=False,
        )
        embed.add_field(
            name="!aotw <queue> pop",
            value="Manually post the next normal AOTW (bot owner only).",
            inline=False,
        )
        embed.add_field(
            name="!aotw help",
            value="Show this help message.",
            inline=False,
        )
        await ctx.send(embed=embed)

    # Add album to queue (interactive search + selection)
    async def add_album(ctx, queue, args: str):
        raw, suggested_user_id = _parse_suggested_user_id(args.strip() if args else "")

        if not raw:
            return await ctx.send("❌ Please provide an album to add.")

        async with ctx.typing():
            if is_lastfm_album_url(raw):
                data = await bot.fetch_album_from_url(raw)
            else:
                data = await bot.fetch_fuzzy_album(raw)

            if not data:
                return await ctx.send("❌ Not found.")

            artist_name = _artist_name(data.get("artist"))
            album_name = data.get("name")
            album_url = data.get("url", "")

            images = data.get("image", []) or []
            img = ""
            # Loop backwards from 'extralarge' to 'small' to find the first non-empty URL
            for image in reversed(images):
                if image.get("#text"):
                    img = image["#text"]
                    break

            if suggested_user_id is not None:
                user_id = suggested_user_id
                user_name = await _resolve_user_name(
                    bot, ctx.guild, suggested_user_id
                )
            else:
                user_id = ctx.author.id
                user_name = ctx.author.display_name

            queue.append(
                {
                    "artist": artist_name,
                    "title": album_name,
                    "url": album_url,
                    "image": img,
                    "user_name": user_name,
                    "user_id": user_id,
                }
            )
            bot.save_queues()

            # Confirmation embed with album cover
            confirm_embed = discord.Embed(
                title=f"{artist_name} - {album_name}",
                description=f"Added to queue.\nSuggested by: {user_name}",
                color=0x2ECC71,
            )
            if img:
                confirm_embed.set_thumbnail(url=img)

            await ctx.send(content="✅ Added to queue:", embed=confirm_embed)

    # Show selected queue
    async def show_queue(ctx, queue):
        if not queue:
            return await ctx.send("Empty.")
        embed = discord.Embed(
            title="Upcoming Album Queue",
            description=f"There are **{len(queue)}** albums waiting.",
            color=0x3498DB,
        )
        for i, item in enumerate(queue[:5], 1):
            user_id = item.get("user_id")
            submitter = f"<@{user_id}>" if user_id else item.get("user_name", "Unknown")
            embed.add_field(
                name=f"{i}.",
                value=(
                    f"{_album_title_link(item)}\n"
                    f"Artist: {_artist_name(item.get('artist'))}\n"
                    f"Submitted by: {submitter}"
                ),
                inline=False,
            )

        first_img = queue[0]["image"]
        if first_img:
            embed.set_thumbnail(url=first_img)

        await ctx.send(embed=embed)

    # Remove album from queue by 1-based index
    async def remove_album(ctx, queue, index: int):
        if index < 1:
            return await ctx.send("❌ Index must be 1 or greater.")
        if not queue:
            return await ctx.send("❌ Queue is empty.")
        if index > len(queue):
            return await ctx.send(
                f"❌ Index out of range. There are {len(queue)} items."
            )

        removed = queue.pop(index - 1)
        bot.save_queues()
        await ctx.send(
            f"✅ Removed **{removed.get('artist')} - {removed.get('title')}** from queue."
        )

    # Manually pop queue (bot owner only)
    async def pop_queue(ctx, queue):
        result = await bot.post_album(queue)
        if result:
            await ctx.send(f"Manually triggered post for: **{result}**")
        else:
            await ctx.send("Queue is empty.")

    # Helper to create analogous commands for standard and bonus queues
    def register_queue_commands(group, queue):
        @group.command(name="add")
        async def _add(ctx, *, args=None):
            await add_album(ctx, queue, args)

        @group.command(name="queue")
        async def _list(ctx):
            await show_queue(ctx, queue)

        @group.command(name="remove")
        async def _remove(ctx, index: int):
            await remove_album(ctx, queue, index)

        @group.command(name="pop")
        @commands.is_owner()
        async def _pop(ctx):
            await pop_queue(ctx, queue)

    register_queue_commands(normal, bot.store.main)
    register_queue_commands(bonus, bot.store.bonus)
