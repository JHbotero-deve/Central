from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    print("Endpoint raíz (/):", response.json())
    assert response.status_code == 200

def test_admin_products():
    response = client.get("/admin/products")
    print("Endpoint admin productos (/admin/products):", response.json())
    assert response.status_code == 200

if __name__ == "__main__":
    test_root()
    test_admin_products()
    print("¡Todos los endpoints responden correctamente!")
