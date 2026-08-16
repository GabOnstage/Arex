import discord
from discord.ext import commands
import aiohttp
from datetime import datetime, timezone
import asyncio

class F1Info(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="f1", description="Gets information and standings for the latest Formula 1 race.")
    async def f1(self, ctx: commands.Context) -> None:
        await ctx.defer()
        
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            # 1. Fetch race sessions
            async with session.get('https://api.openf1.org/v1/sessions?session_type=Race', timeout=10) as response:
                if response.status != 200:
                    await ctx.send(f"Failed to fetch F1 sessions (Status: {response.status}).")
                    return
                sessions = await response.json()

            now = datetime.now(timezone.utc).isoformat()
            past_sessions = [s for s in sessions if s.get('date_start', '') and s.get('date_start', '') < now]
            if not past_sessions:
                await ctx.send("No past Formula 1 race sessions found.")
                return

            past_sessions.sort(key=lambda x: x['date_start'])
            latest_session = past_sessions[-1]
            session_key = latest_session.get('session_key')

            race_name = latest_session.get('session_name', 'Race')
            date_str = latest_session.get('date_start', '').split('T')[0]
            circuit = latest_session.get('circuit_short_name', 'Unknown Circuit')
            location = latest_session.get('location', 'Unknown Location')
            country = latest_session.get('country_name', 'Unknown Country')

            # 2. Fetch drivers, positions, and laps in parallel
            drivers_req = session.get(f'https://api.openf1.org/v1/drivers?session_key={session_key}', timeout=10)
            positions_req = session.get(f'https://api.openf1.org/v1/position?session_key={session_key}', timeout=10)
            laps_req = session.get(f'https://api.openf1.org/v1/laps?session_key={session_key}', timeout=10)

            res_drivers, res_positions, res_laps = await asyncio.gather(
                drivers_req, positions_req, laps_req, return_exceptions=True
            )

            drivers = await res_drivers.json() if not isinstance(res_drivers, Exception) and res_drivers.status == 200 else []
            positions = await res_positions.json() if not isinstance(res_positions, Exception) and res_positions.status == 200 else []
            laps = await res_laps.json() if not isinstance(res_laps, Exception) and res_laps.status == 200 else []

            driver_map = {d.get('driver_number'): d for d in drivers if isinstance(d, dict) and 'driver_number' in d}

            # 3. Determine latest position for each driver
            latest_pos = {}
            for p in positions:
                if not isinstance(p, dict):
                    continue
                dn = p.get('driver_number')
                p_date = p.get('date', '')
                if dn not in latest_pos or p_date > latest_pos[dn].get('date', ''):
                    latest_pos[dn] = p

            # 4. Compute lap count and fastest lap for each driver
            driver_stats = {}
            for l in laps:
                if not isinstance(l, dict):
                    continue
                dn = l.get('driver_number')
                if dn not in driver_stats:
                    driver_stats[dn] = {'laps': 0, 'fastest_lap': None}

                lap_num = l.get('lap_number')
                if isinstance(lap_num, int):
                    driver_stats[dn]['laps'] = max(driver_stats[dn]['laps'], lap_num)

                dur = l.get('lap_duration')
                if dur is not None and isinstance(dur, (int, float)) and dur > 0:
                    if driver_stats[dn]['fastest_lap'] is None or dur < driver_stats[dn]['fastest_lap']:
                        driver_stats[dn]['fastest_lap'] = dur

            # 5. Compile and sort results
            results = []
            for dn, pos_data in latest_pos.items():
                driver = driver_map.get(dn, {})
                stats = driver_stats.get(dn, {'laps': 0, 'fastest_lap': None})
                pos = pos_data.get('position', 99)
                results.append({
                    'position': pos,
                    'driver_number': dn,
                    'driver_name': driver.get('full_name', f"Driver #{dn}"),
                    'team': driver.get('team_name', 'Unknown Team'),
                    'laps': stats['laps'],
                    'fastest_lap': stats['fastest_lap']
                })

            results.sort(key=lambda x: x['position'])

            # 6. Build the Discord Embed
            embed = discord.Embed(
                title=f"🏁 F1 Results: {race_name} ({circuit})",
                description=f"📍 **Location:** {location}, {country}\n📅 **Date:** {date_str}",
                color=discord.Color.red()
            )
            embed.set_thumbnail(url="https://logosarchive.com/wp-content/uploads/2021/06/F1-icon-square.png")
            embed.set_footer(text="Data provided by OpenF1 API")

            if not results:
                embed.add_field(name="Results", value="No driver standing data available for this race.", inline=False)
            else:
                medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                rows = []
                for r in results[:10]:
                    pos_badge = medals.get(r['position'], f"`P{r['position']:02d}`")
                    fastest = f"{r['fastest_lap']:.3f}s" if isinstance(r['fastest_lap'], (int, float)) else "N/A"
                    rows.append(
                        f"{pos_badge} **{r['driver_name']}** ({r['team']})\n"
                        f"┗ Laps: `{r['laps']}` | Fastest: `{fastest}`"
                    )

                embed.add_field(name="Top 10 Classification", value="\n\n".join(rows), inline=False)

            await ctx.send(embed=embed)

        except asyncio.TimeoutError:
            await ctx.send("OpenF1 API timed out. Please try again later.")
        except Exception as e:
            await ctx.send(f"An error occurred while fetching F1 data: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(F1Info(bot))
