import datetime
from typing import Literal, Union

import discord
from discord.http import Route
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands.converter import TimedeltaConverter
from redbot.core.config import Config

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Timeout(commands.Cog):
    """
    manage cooldowns
    """

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=202342309123,
            force_registration=True,
        )

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # TODO: Replace this with the proper end user data removal handling.
        super().red_delete_data_for_user(requester=requester, user_id=user_id)

    async def is_user_timed_out(self, member: discord.Member) -> bool:
        r = Route(
            "GET",
            "/guilds/{guild_id}/members/{user_id}",
            guild_id=member.guild.id,
            user_id=member.id,
        )
        try:
            data = await self.bot.http.request(r)
        except discord.NotFound:
            return False
        return data["communication_disabled_until"] is not None

    async def timeout_user(
        self,
        ctx: commands.Context,
        member: discord.Member,
        time: datetime.timedelta,
        reason: str = None,
    ) -> None:
        r = Route(
            "PATCH",
            "/guilds/{guild_id}/members/{user_id}",
            guild_id=ctx.guild.id,
            user_id=member.id,
        )

        payload = {
            "communication_disabled_until": str(
                datetime.datetime.now(datetime.timezone.utc) + time
            )
            if time
            else None
        }

        await ctx.bot.http.request(r, json=payload, reason=reason)

    async def timeout_role(
        self,
        ctx: commands.Context,
        role: discord.Role,
        time: datetime.timedelta,
        reason: str = None,
    ) -> None:
        failed = []
        members = list(role.members)
        for member in members:
            try:
                await self.timeout_user(ctx, member, time, reason)
            except discord.HTTPException:
                failed.append(member)
        return failed

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 1, commands.BucketType.user)
    @commands.mod_or_permissions(administrator=True)
    async def timeout(
        self,
        ctx: commands.Context,
        member_or_role: Union[discord.Member, discord.Role],
        time: TimedeltaConverter(
            minimum=datetime.timedelta(minutes=1),
            maximum=datetime.timedelta(days=28),
            default_unit="minutes",
            allowed_units=["minutes", "seconds", "hours", "days"],
        ) = None,
        *,
        reason: str = None,
    ):
        if not time:
            time = datetime.timedelta(seconds=60)
        timestamp = datetime.datetime.now(datetime.timezone.utc) + time
        timestamp = int(datetime.datetime.timestamp(timestamp))
        if isinstance(member_or_role, discord.Member):
            check = await is_allowed_by_hierarchy(ctx.bot, ctx.author, member_or_role)
            if not check:
                return await ctx.send("You cannot timeout this user due to hierarchy.")
            if member_or_role.permissions_in(ctx.channel).administrator:
                return await ctx.send("You can't timeout an administrator.")
            await self.timeout_user(ctx, member_or_role, time, reason)
            await ctx.send(
                f"{member_or_role.mention} has been timed out till <t:{timestamp}:f>."
            )
        else:
            await ctx.send(
                f"Timeing out {len(member_or_role.members)} members till <t:{timestamp}:f>."
            )
            failed = await self.timeout_role(ctx, member_or_role, time, reason)
            await ctx.send(f"Failed to timeout {len(failed)} members.")

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 1, commands.BucketType.user)
    @commands.mod_or_permissions(administrator=True)
    async def untimeout(
        self,
        ctx: commands.Context,
        member_or_role: Union[discord.Member, discord.Role],
        *,
        reason: str = None,
    ):
        is_timedout = await self.is_user_timed_out(member_or_role)
        if isinstance(member_or_role, discord.Member):
            if not is_timedout:
                return await ctx.send("This user is not timed out.")
            await self.timeout_user(ctx, member_or_role, None, reason)
            return await ctx.send(f"Removed timeout from {member_or_role.mention}")
        if isinstance(member_or_role, discord.Role):
            await ctx.send(
                f"Removing timeout from {len(member_or_role.members)} members."
            )
            members = list(member_or_role.members)
            for member in members:
                if await self.is_user_timed_out(member):
                    await self.timeout_user(ctx, member, None, reason)
            return await ctx.send(f"Removed timeout from {len(members)} members.")


# https://github.com/phenom4n4n/phen-cogs/blob/8727d6ee74b40709c7eb9300713dc22b88a17915/roleutils/utils.py#L34
async def is_allowed_by_hierarchy(
    bot: Red, user: discord.Member, member: discord.Member
) -> bool:
    return (
        user.guild.owner_id == user.id
        or user.top_role > member.top_role
        or await bot.is_owner(user)
    )
