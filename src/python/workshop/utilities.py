from pathlib import Path

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import ThreadMessage
from azure.core.exceptions import ClientAuthenticationError
from azure.identity.aio import DefaultAzureCredential
from terminal_colors import TerminalColors as tc


class Utilities:
    # property to get the relative path of shared files
    @property
    def shared_files_path(self) -> Path:
        """Get the path to the shared files directory."""
        return Path(__file__).parent.parent.parent.resolve() / "shared"

    async def validate_azure_authentication(self) -> DefaultAzureCredential:
        """Validate Azure authentication before proceeding."""
        try:
            credential = DefaultAzureCredential()
            # Test credential by getting a token
            token = await credential.get_token("https://management.azure.com/.default")
            return credential
        except ClientAuthenticationError as e:
            print(f"{tc.BG_BRIGHT_RED}❌ Azure Authentication Failed{tc.RESET}")
            print("\n🔧 To fix this issue, please run the following command:")
            print(f"{tc.CYAN}Azure CLI:{tc.RESET}")
            print("   az login --use-device-code")
            print(f"\n{tc.YELLOW}After authentication, run the program again.{tc.RESET}")
            raise e
        
    @property
    def get_credential(self) -> DefaultAzureCredential:
        """Get the Azure credential."""
        return DefaultAzureCredential()

    def load_instructions(self, instructions_file: str) -> str:
        """Load instructions from a file."""
        file_path = self.shared_files_path / instructions_file
        with file_path.open("r", encoding="utf-8", errors="ignore") as file:
            return file.read()

    def log_msg_green(self, msg: str) -> None:
        """Print a message in green."""
        print(f"{tc.GREEN}{msg}{tc.RESET}")

    def log_msg_purple(self, msg: str) -> None:
        """Print a message in purple."""
        print(f"{tc.PURPLE}{msg}{tc.RESET}")

    def log_token_blue(self, msg: str) -> None:
        """Print a token in blue."""
        print(f"{tc.BLUE}{msg}{tc.RESET}", end="", flush=True)

    async def get_file(self, agents_client: AgentsClient, file_id: str, attachment_name: str) -> None:
        """Retrieve the file and save it to the local disk."""
        self.log_msg_green(f"Getting file with ID: {file_id}")

        attachment_part = attachment_name.split(":")[-1]
        file_name = Path(attachment_part).stem
        file_extension = Path(attachment_part).suffix
        if not file_extension:
            file_extension = ".png"
        file_name = f"{file_name}.{file_id}{file_extension}"

        folder_path = Path(self.shared_files_path) / "files"
        folder_path.mkdir(parents=True, exist_ok=True)
        file_path = folder_path / file_name
        print(f"Saving file to: {file_path}")

        # Save the file using a synchronous context manager
        with file_path.open("wb") as file:
            async for chunk in await agents_client.files.get_content(file_id):
                file.write(chunk)

        self.log_msg_green(f"File saved to {file_path}")

    async def get_files(self, message: ThreadMessage, agents_client: AgentsClient) -> None:
        """Get the image files from the message and kickoff download."""
        if message.image_contents:
            for index, image in enumerate(message.image_contents, start=0):
                attachment_name = (
                    "unknown"
                    if not message.file_path_annotations
                    else message.file_path_annotations[index].text + ".png"
                )
                await self.get_file(agents_client, image.image_file.file_id, attachment_name)
        elif message.attachments:
            for index, attachment in enumerate(message.attachments, start=0):
                attachment_name = (
                    "unknown" if not message.file_path_annotations else message.file_path_annotations[index].text
                )
                if attachment.file_id:
                    await self.get_file(agents_client, attachment.file_id, attachment_name)

    async def upload_file(self, agents_client: AgentsClient, file_path: Path, purpose: str = "assistants"):
        """Upload a file to the project."""
        self.log_msg_purple(f"Uploading file: {file_path}")
        file_info = await agents_client.files.upload(file_path=str(file_path), purpose=purpose)
        self.log_msg_purple(f"File uploaded with ID: {file_info.id}")
        return file_info

    async def create_vector_store(self, agents_client: AgentsClient, files: list[str], vector_store_name: str):
        """Upload a file to the project."""

        file_ids = []
        prefix = self.shared_files_path

        # Upload the files
        for file in files:
            file_path = prefix / file
            file_info = await self.upload_file(agents_client, file_path=file_path, purpose="assistants")
            file_ids.append(file_info.id)

        self.log_msg_purple("Creating the vector store")

        # Create a vector store
        vector_store = await agents_client.vector_stores.create_and_poll(file_ids=file_ids, name=vector_store_name)

        self.log_msg_purple("Vector store created and files added.")
        return vector_store
