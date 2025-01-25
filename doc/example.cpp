#include <iostream>
#include <format>

int main(int argc, char** argv)
{
    std::cout << "Hello World!" << std::endl;

    std::cout << std::format("And here are some numbers: {}, {}, {}\n", 0x123, 15, 3.14);

    auto lambda = [](auto& stream) {
        stream << "... and goodbye!\n";
        stream.flush();
    };

    lambda(std::cout);

    return 0;
}
