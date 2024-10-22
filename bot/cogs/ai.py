from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Literal

from discord import (
    Attachment,
    Colour,
    Embed,
    Interaction,
    Message,
    app_commands,
    ui,
)
from discord.ext import commands
from openai import AsyncOpenAI
from utils.consts import ai_ban_words
from utils.gpt import about_text

if TYPE_CHECKING:
    from ..bot import Konikotaka


class Download(ui.View):
    def __init__(self, url: str):
        super().__init__()
        self.add_item(ui.Button(label="Download your image here!", url=url))


class Ai(commands.Cog):
    def __init__(self, client: Konikotaka) -> None:
        self.client: Konikotaka = client
        self.openai_token: str = os.environ["OPENAI_TOKEN"]
        self.openai_gateway_url: str = os.environ["CLOUDFLARE_AI_GATEWAY_URL"]
        self.openai_client = AsyncOpenAI(
            api_key=self.openai_token, base_url=self.openai_gateway_url
        )

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author == self.client.user:
            return
        if message.mention_everyone:
            return
        if self.client.user.mentioned_in(message):
            name = message.author.nick if message.author.nick else message.author.name
            chat_completion = await self.openai_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": about_text
                        + f"when you answer someone, answer them by {name}",
                    },
                    {
                        "role": "user",
                        "content": message.content.strip(f"<@!{self.client.user.id}>"),
                    },
                ],
                model="gpt4o",
            )
            await message.channel.typing()
            await message.channel.send(chat_completion.choices[0].message.content)

    @app_commands.command(
        name="imagine", description="Generate an image using OpenAI's DALL-E"
    )
    @app_commands.guild_only()
    @app_commands.describe(prompt="The prompt to generate an image from")
    async def imagine(
        self,
        interaction: Interaction,
        prompt: str,
        size: Literal["1024x1024", "1792x1024", "1024x1792"],
        style: Literal["vivid", "natural"],
    ) -> None:
        await interaction.response.defer()
        if any(word in prompt for word in ai_ban_words):
            await interaction.edit_original_response(
                content="Your prompt contains a banned word. Please try again."
            )
            return

        start_time = time.time()
        try:
            image_data = await self.openai_client.images.generate(
                prompt=prompt,
                model="dall-e-3",
                n=1,
                quality="hd",
                response_format="url",
                size=size,
                style=style,
                user=interaction.user.name,
            )
        except Exception as e:
            self.client.log.error(f"Error generating image: {e}")
            await interaction.edit_original_response(
                content="An error occurred during generation. This has been reported to the developers - {interaction.user.mention}"
            )
            return

        if image_data.data[0].url:
            self.client.log.info(
                f"Image generated generated by {interaction.user.name} with prompt: {prompt}"
            )

            elapsed_time = time.time() - start_time
            embed = Embed()
            embed.title = "Result for your prompt"
            embed.colour = Colour.blurple()
            embed.description = f"```{prompt}```"
            embed.set_image(url=image_data.data[0].url)
            embed.set_footer(
                text=f"Took {elapsed_time:.2f}s - Note: This URL will expire in 60 minutes"
            )
            await interaction.edit_original_response(
                embed=embed, view=Download(url=image_data.data[0].url)
            )
        else:
            self.client.log.error(f"Error generating image: {image_data.data}")
            await interaction.edit_original_response(
                content=f"An error occurred during generation. This has been reported to the developers - {interaction.user.mention}"
            )

    @app_commands.command(
        name="describe", description="Describe an image using MicrosoftAI"
    )
    @app_commands.guild_only()
    @app_commands.describe(photo="The photo to describe")
    async def describe(self, interaction: Interaction, photo: Attachment) -> None:
        await interaction.response.defer()
        url = f"{os.getenv('CLOUDFLARE_AI_URL')}/@cf/microsoft/resnet-50"
        headers = {"Authorization": f"Bearer {os.getenv('CLOUDFLARE_AI_TOKEN')}"}
        try:
            image_binary = await photo.read()
        except Exception as e:
            self.client.log.error(f"Error reading image: {e}")
            await interaction.edit_original_response(
                content="An error occurred while reading your image"
            )
            return
        if len(image_binary) > 4_000_000:
            await interaction.edit_original_response(
                content="Your image is too large. Please try again with an image smaller than 4MB"
            )
            return
        start_time = time.time()
        try:
            response = await self.client.session.post(
                url=url, headers=headers, data=image_binary
            )
        except Exception as e:
            self.client.log.error(f"Error describing image: {e}")
            await interaction.edit_original_response(
                content="An error occurred while describing your image, please try again"
            )
            return
        if response.status == 200:
            data = await response.json()
            image_description = data["result"]
            embed = Embed()
            embed.title = "Description for your image"
            embed.colour = Colour.blurple()
            description = ""
            for i in image_description:
                description += f"Label: **{i['label']}** Score: **{round(i['score'] * 100, 2)}**\n\n"

            embed.description = description
            embed.set_image(url=photo.url)
            elapsed_time = time.time() - start_time
            embed.set_footer(text=f"Took {elapsed_time:.2f}s")
            await interaction.edit_original_response(embed=embed)
        else:
            self.client.log.error(
                f"Error describing image: {response.status} {response.reason}"
            )
            await interaction.edit_original_response(
                content="An error occurred while describing your image"
            )


async def setup(client: Konikotaka) -> None:
    await client.add_cog(Ai(client))
